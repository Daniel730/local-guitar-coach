"""WebSocket handler for real-time audio processing."""
from __future__ import annotations
from typing import Optional
import json
import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.services.session_service import SessionService
from app.models.session import SessionStateTelemetry, ErrorTelemetry

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket lifecycle and message routing."""

    def __init__(self, session_service: SessionService) -> None:
        self.session_service = session_service
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_by_session: dict[str, WebSocket] = {}

    async def handle(self, websocket: WebSocket) -> None:
        """Main WebSocket handler."""
        await websocket.accept()
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        session_id: Optional[str] = None

        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    logger.info("WebSocket disconnected")
                    break
                if msg.get("text"):
                    session_id = await self._handle_text(websocket, msg["text"], session_id)
                # NOTE: browser no longer uploads binary audio — capture is done
                # server-side via sounddevice. Ignore any binary frames.
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.exception("WebSocket error")
            await self._send_error(websocket, str(e))
        finally:
            # Closing or reloading the tab must release the device and the session.
            if session_id:
                self._cleanup(session_id)

    async def _handle_text(self, websocket: WebSocket, text: str, current_session_id) -> Optional[str]:
        try:
            data = json.loads(text)
            msg_type = data.get("type")
            if msg_type == "start_session":
                sid = await self._start_session(websocket, data)
                return sid
            elif msg_type == "stop_session":
                if current_session_id:
                    self._cleanup(current_session_id)
                return current_session_id
            else:
                await self._send_error(websocket, f"Unknown message type: {msg_type}")
                return current_session_id
        except Exception as e:
            await self._send_error(websocket, f"Error: {e}")
            return current_session_id

    async def _start_session(self, websocket: WebSocket, data: dict) -> str:
        """Create a session, start physical capture, register emitter."""
        exercise_id = data.get("exercise_id", "scale_e_minor_001")
        channel = data.get("channel", 1)
        sample_rate = data.get("sample_rate", 44100)
        block_size = data.get("block_size", 1024)
        device = data.get("device", 1)   # M-Track idx
        gain = data.get("gain", 4.0)
        amplitude_floor = data.get("amplitude_floor", 0.01)

        session = self.session_service.create_session(
            exercise_id=exercise_id, channel=channel,
            sample_rate=sample_rate, block_size=block_size, device=device,
            gain=gain, amplitude_floor=amplitude_floor,
        )
        session_id = session.session_id
        self._ws_by_session[session_id] = websocket

        # Register emitter: thread-safe push via call_soon_threadsafe
        async def _send(data: dict) -> None:
            try:
                await websocket.send_text(json.dumps(data))
            except Exception:
                pass
        def emit(data: dict) -> None:
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(lambda: asyncio.create_task(_send(data)))
        self.session_service.register_emitter(session_id, emit)

        # Start physical capture (sounddevice) — measures channels + opens stream
        try:
            channels_dbfs = await self._loop.run_in_executor(
                None, self.session_service.start_capture, session_id)
            await _send({"type": "channels_dbfs", "channels": channels_dbfs})
            if channels_dbfs:
                await _send({"type": "meter_message",
                             "ch1": channels_dbfs[0] if len(channels_dbfs) > 0 else None,
                             "ch2": channels_dbfs[1] if len(channels_dbfs) > 1 else None})
        except Exception as e:
            logger.exception("Capture start failed")
            await _send({"type": "error",
                         "message": f"Não consegui abrir a entrada de áudio ({e}). "
                                    "Confira se a M-Track está ligada e tente de novo."})

        # Teacher task
        task = asyncio.create_task(self._teacher_loop(session_id))
        self._teacher_task = task

        await _send(SessionStateTelemetry(
            status="running", exercise=exercise_id, target_bpm=session.target_bpm,
        ).model_dump())
        return session_id

    def _cleanup(self, session_id: str) -> None:
        self.session_service.stop_session(session_id)
        if session_id in self._ws_by_session:
            del self._ws_by_session[session_id]
        task = getattr(self, "_teacher_task", None)
        if task:
            task.cancel()

    async def _teacher_loop(self, session_id: str) -> None:
        """Close attempts as they complete: one teacher decision per attempt."""
        try:
            while True:
                await asyncio.sleep(0.25)
                session = self.session_service.get_session(session_id)
                if not session or session.status != "running":
                    break
                teacher_svc = self.session_service.get_teacher_service(session_id)
                ws = self._ws_by_session.get(session_id)
                if teacher_svc and ws and teacher_svc.attempt_ready():
                    try:
                        msgs = await self._loop.run_in_executor(
                            None, self.session_service.close_attempt, session_id)
                        for m in msgs:
                            await ws.send_text(json.dumps(m))
                    except Exception:
                        logger.exception("Teacher decision/send error")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Teacher loop error")

    async def _send_json(self, websocket: WebSocket, data: dict) -> None:
        try:
            await websocket.send_text(json.dumps(data))
        except Exception:
            pass

    async def _send_error(self, websocket: WebSocket, message: str) -> None:
        await self._send_json(websocket, ErrorTelemetry(message=message).model_dump())


ws_handler: Optional[WebSocketHandler] = None