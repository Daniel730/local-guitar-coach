"""MVP-6 gate steps 1-4 without hardware: synthetic guitar audio injected at the
sounddevice boundary -> real PerceptionEngine/EventTracker -> WebSocket telemetry.

Blocks are hardware-sized (1024 @ 44100) on CH2, as the M-Track delivers them.
"""
import json
import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from ai.teacher import FakeLLMProvider
from perception.notes import note_to_freq

SR, BS = 44100, 1024
SCALE = ["E2", "G2", "A2", "B2", "D3", "E3"]


def _synth(notes, note_s=0.6, gap_s=0.15):
    parts = []
    for n in notes:
        t = np.arange(int(SR * note_s)) / SR
        f = note_to_freq(n)
        tone = sum(np.sin(2 * np.pi * f * k * t) / k for k in (1, 2, 3))
        parts += [0.3 * tone * np.exp(-1.5 * t), np.zeros(int(SR * gap_s))]
    mono = np.concatenate(parts + [np.zeros(SR)])
    stereo = np.zeros((len(mono), 2), dtype=np.float32)
    stereo[:, 1] = mono  # guitar on CH2 (Hi-Z), CH1 silent
    return stereo


class FakeStream:
    """Stands in for audio_probe.stream.AudioStream: plays synthetic blocks."""

    def __init__(self, cfg, device, on_meter=None):
        self._callback = lambda *a: None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        audio = _synth(SCALE)

        def run():
            for i in range(0, len(audio) - BS, BS):
                if self._stop.is_set():
                    return
                self._callback(audio[i:i + BS], BS, None, None)
                time.sleep(0.002)  # faster than real time; engine uses sample time

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


def test_synthetic_session_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.audio_service._PortAudioStream", FakeStream)
    monkeypatch.setattr("app.services.teacher_service.OllamaProvider",
                        lambda **kw: FakeLLMProvider(mode="unavailable"))
    monkeypatch.setattr("perception.persistence._session_dir", lambda: tmp_path)
    from app.main import app

    seen = {}
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:  # `with` runs lifespan
        ws.send_text(json.dumps({"type": "start_session", "exercise_id": "scale_e_minor_001",
                                 "device": 0, "channel": 1, "gain": 1.0}))
        deadline = time.time() + 30
        while time.time() < deadline and "teacher" not in seen:
            msg = json.loads(ws.receive_text())
            seen.setdefault(msg["type"], msg)
            if msg["type"] == "note_event":
                seen.setdefault("notes", []).append(msg["note"])
        ws.send_text(json.dumps({"type": "stop_session"}))

    assert seen["session_state"]["status"] == "running"
    assert seen["channels_dbfs"]["channels"][1] > seen["channels_dbfs"]["channels"][0]
    assert {"pitch", "meter", "note_event", "attempt_result", "teacher"} <= seen.keys()
    assert seen["notes"] == SCALE
    assert seen["attempt_result"]["performance"]["note_accuracy"] == 1.0
    teacher = seen["teacher"]
    assert teacher["source"] == "fallback"           # Ollama down -> session survives
    assert teacher["exercise_id"] == "scale_e_minor_001"
