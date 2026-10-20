"""SessionService — manages active WebSocket sessions."""
from __future__ import annotations
import logging
import os
from typing import Dict, Optional, Callable, Any, List
import uuid

from app.models.session import Session
from app.services.audio_service import AudioService, AudioConfig
from app.services.teacher_service import TeacherService
from perception.engine import MusicalEvent
from perception.events import NoteEvent
from perception.performance import PerformanceResult
from perception.skill import SkillStateTracker, SkillState
from perception.notes import freq_to_midi
from perception import persistence

logger = logging.getLogger(__name__)

# Emitter: Callable[[dict], None] — a function the WebSocket handler registers
# per session to push a telemetry dict to the connected browser.
Emitter = Callable[[dict], None]


class SessionService:
    """Manages active WebSocket sessions (in-memory, single-user MVP)."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._audio_services: Dict[str, AudioService] = {}
        self._teacher_services: Dict[str, TeacherService] = {}
        self._emitters: Dict[str, Emitter] = {}

    def register_emitter(self, session_id: str, emit: Emitter) -> None:
        """Register the WebSocket-outbound callback for a session."""
        self._emitters[session_id] = emit

    def _emit(self, session_id: str, data: dict) -> None:
        emit = self._emitters.get(session_id)
        if emit:
            emit(data)

    def create_session(
        self,
        exercise_id: str,
        channel: int,
        sample_rate: int,
        block_size: int,
        device: int = 1,
        gain: float = 4.0,
        amplitude_floor: float = 0.01,
    ) -> Session:
        """Create a new session."""
        logger.info("[session] create_session exercise=%s ch=%s sr=%s bs=%s dev=%s gain=%s floor=%s",
                    exercise_id, channel, sample_rate, block_size, device, gain, amplitude_floor)
        session_id = str(uuid.uuid4())[:8]
        # Tempo is a property of the exercise (CHANGE-05). Load it from the
        # exercise definition; fail visibly if the exercise lacks tempo.
        from exercises.exercise import load_exercise
        ex = load_exercise(f"exercises/{exercise_id}.json")
        if ex.target_bpm is None or ex.subdivision is None:
            raise ValueError(f"Exercise {exercise_id} missing tempo (target_bpm/subdivision)")
        tempo = {
            "target_bpm": ex.target_bpm,
            "subdivision": ex.subdivision,
            "start_bpm": ex.start_bpm if ex.start_bpm is not None else ex.target_bpm,
        }

        session = Session(
            exercise_id=exercise_id,
            channel=channel,
            sample_rate=sample_rate,
            block_size=block_size,
            target_bpm=tempo["target_bpm"],
            subdivision=tempo["subdivision"],
            start_bpm=tempo["start_bpm"],
            session_id=session_id,
        )
        self._sessions[session_id] = session

        # Audio service (lazy; capture started separately via start_capture to
        # avoid opening the device until the user explicitly starts a session)
        audio_cfg = AudioConfig(
            device=device,            # M-Track: 1 (MME) / 25 (WASAPI)
            sample_rate=sample_rate,
            block_size=block_size,
            channel=channel,
            gain=gain,
            amplitude_floor=amplitude_floor,
        )
        audio_svc = AudioService(
            config=audio_cfg,
            on_pitch=self._make_pitch_callback(session_id),
            on_note_event=self._make_note_event_callback(session_id),
            on_meter=self._make_meter_callback(session_id),
        )
        self._audio_services[session_id] = audio_svc

        # Teacher service
        teacher_svc = TeacherService(
            exercise_id=exercise_id,
            ollama_model=os.environ.get("RIFF_OLLAMA_MODEL", "llama3.1:8b"),
            fail_ollama=False,
        )
        self._teacher_services[session_id] = teacher_svc

        logger.info("[session] created session_id=%s exercise=%s target_bpm=%s sub=%s",
                    session_id, exercise_id, tempo["target_bpm"], tempo["subdivision"])
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_audio_service(self, session_id: str) -> Optional[AudioService]:
        return self._audio_services.get(session_id)

    def get_teacher_service(self, session_id: str) -> Optional[TeacherService]:
        return self._teacher_services.get(session_id)

    def start_capture(self, session_id: str) -> List[float]:
        """Measure channels and start physical capture for a session. Returns channel dBFS."""
        logger.info("[session] start_capture session_id=%s", session_id)
        audio_svc = self._audio_services.get(session_id)
        if not audio_svc:
            logger.warning("[session] start_capture: no audio service for session_id=%s", session_id)
            return []
        channels_dbfs = audio_svc.measure_channels(seconds=1.0)
        audio_svc.start()
        logger.info("[session] start_capture session_id=%s channels_dbfs=%s", session_id, channels_dbfs)
        return channels_dbfs

    def close_attempt(self, session_id: str) -> List[dict]:
        """Close the current attempt: one teacher decision + persistence.

        Returns the telemetry messages to send (attempt_result, teacher).
        Runs in an executor thread (the teacher may call Ollama).
        """
        teacher_svc = self._teacher_services.get(session_id)
        if not teacher_svc:
            return []
        teacher_svc.close_attempt()
        state = self.persist_session(session_id)
        msgs = [{
            "type": "attempt_result",
            "attempt": teacher_svc.attempt_count,
            "exercise_id": teacher_svc.exercise_id,
            "performance": teacher_svc.get_performance_telemetry(),
            "skill": state.to_dict() if state is not None else None,
        }]
        telemetry = teacher_svc.get_teacher_telemetry()
        if telemetry:
            msgs.append(telemetry)
        return msgs

    def persist_session(self, session_id: str) -> Optional[SkillState]:
        """Persist performance + skill state for the latest evaluated attempt.

        Idempotent per attempt: a performance is persisted at most once.
        Returns the updated SkillState (None when nothing was persisted).
        """
        logger.info("[session] persist_session session_id=%s", session_id)
        session = self._sessions.get(session_id)
        teacher_svc = self._teacher_services.get(session_id)
        if not session or not teacher_svc:
            logger.warning("[session] persist_session: missing session or teacher for %s", session_id)
            return None
        perf = teacher_svc._performance  # PerformanceResult or None
        if perf is None:
            logger.info("[session] persist_session: no performance data for %s", session_id)
            return None
        if getattr(teacher_svc, "performance_persisted", False):
            return None
        # Persist the per-session performance result (P1-B part 1)
        # One file per attempt so attempts don't overwrite each other.
        attempt = getattr(teacher_svc, "attempt_count", 0)
        record_id = f"{session_id}_a{attempt}" if attempt else session_id
        persistence.save_performance(perf, session_id=record_id)
        # Update + persist the skill state (P1-B part 2)
        skill = getattr(teacher_svc.exercise, "skill", None) or "unknown"
        try:
            state = persistence.load_skill_state(skill) or SkillState(skill=skill)
        except Exception:
            state = SkillState(skill=skill)
        tracker = SkillStateTracker(skill=skill)
        tracker.update(state, perf, target_bpm=session.target_bpm)
        persistence.save_skill_state(state)
        teacher_svc.performance_persisted = True
        logger.info("[session] persisted session_id=%s skill=%s", session_id, skill)
        return state

    def stop_session(self, session_id: str) -> bool:
        """Stop and cleanup a session."""
        logger.info("[session] stop_session session_id=%s", session_id)
        # Stop capture first so no note events arrive mid-teardown.
        if session_id in self._audio_services:
            self._audio_services[session_id].stop()
        # Evaluate an unfinished attempt (no teacher call) and persist it
        # BEFORE tearing down the teacher service.
        teacher_svc = self._teacher_services.get(session_id)
        if teacher_svc and teacher_svc.has_pending_notes():
            teacher_svc.evaluate_pending()
        self.persist_session(session_id)
        if session_id in self._audio_services:
            del self._audio_services[session_id]
        if session_id in self._teacher_services:
            self._teacher_services[session_id].reset()
            del self._teacher_services[session_id]
        if session_id in self._emitters:
            del self._emitters[session_id]
        if session_id in self._sessions:
            self._sessions[session_id].status = "stopped"
            del self._sessions[session_id]
            return True
        return False

    def _make_pitch_callback(self, session_id: str):
        def callback(ev: MusicalEvent):
            # P2-A: derive cents from frequency (nearest-note offset, ±50).
            # Uses the existing freq_to_midi() from perception/notes.py — no
            # change to the perception core. The frontend already renders this
            # via setCents(data.cents ?? null).
            cents = None
            if ev.frequency and ev.frequency > 0:
                midi_frac = freq_to_midi(ev.frequency)
                if midi_frac is not None:
                    cents = round(100.0 * (midi_frac - round(midi_frac)), 1)
            self._emit(session_id, {
                "type": "pitch",
                "note": ev.note,
                "frequency": round(ev.frequency, 2),
                "cents": cents,
                "confidence": round(ev.confidence, 2),
                "onset": bool(ev.onset),
            })
        return callback

    def _make_note_event_callback(self, session_id: str):
        def callback(ne: NoteEvent):
            session = self._sessions.get(session_id)
            if session:
                session.note_events.append(ne)
                teacher_svc = self._teacher_services.get(session_id)
                if teacher_svc:
                    teacher_svc.add_note_event(ne)
            self._emit(session_id, {
                "type": "note_event",
                "note": ne.note,
                "midi": ne.midi,
                "start": round(ne.start, 3),
                "end": round(ne.end, 3),
                "duration": round(ne.duration, 3),
                "confidence": round(ne.confidence, 2),
                "attack_confidence": round(ne.attack_confidence, 2),
                "uncertain": ne.uncertain,
            })
        return callback

    def _make_meter_callback(self, session_id: str):
        def callback(levels):
            # levels = [rms_db, peak_db]
            self._emit(session_id, {
                "type": "meter",
                "rms_db": round(levels[0], 1),
                "peak_db": round(levels[1], 1),
            })
        return callback