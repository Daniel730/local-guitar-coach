"""Audit fixes: local files stay private, other sites can't drive the app,
closing the tab releases the session, songs don't report ungraded timing."""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai.teacher import FakeLLMProvider
from tests.test_attempts import _ne
from tests.test_e2e_synthetic import FakeStream


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.audio_service._PortAudioStream", FakeStream)
    monkeypatch.setattr("app.services.teacher_service.OllamaProvider",
                        lambda **kw: FakeLLMProvider(mode="unavailable"))
    monkeypatch.setattr("perception.persistence._session_dir", lambda: tmp_path)
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_no_file_outside_frontend_and_no_cors(client):
    assert client.get("/..%2Frequirements.txt").status_code == 404
    r = client.get("/app.js", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_websocket_refuses_other_origins(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"Origin": "http://evil.example"}) as ws:
            ws.receive_text()
    with client.websocket_connect("/ws", headers={"Origin": "http://testserver"}):
        pass


def test_closing_the_tab_cleans_up_the_session(client):
    from app.main import session_service
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "start_session", "exercise_id": "scale_e_minor_001",
                                 "device": 0, "channel": 1}))
        ws.receive_text()
        assert len(session_service._sessions) == 1
    for _ in range(50):
        if not session_service._sessions:
            break
        time.sleep(0.05)
    assert not session_service._sessions


def test_song_hides_ungraded_timing():
    from app.services.teacher_service import TeacherService
    t = TeacherService(exercise_id="song_ode_to_joy_a", fail_ollama=True)
    for i, n in enumerate(t.exercise.expected_sequence):
        t.add_note_event(_ne(n, i * 0.6))
    t.close_attempt()
    perf = t.get_performance_telemetry()
    assert perf["note_accuracy"] == 1.0 and perf["timing_accuracy"] is None
    assert t._performance.timing_accuracy is not None   # stored result keeps raw value


def test_progress_lists_most_recent_first(tmp_path, monkeypatch):
    import asyncio
    from app.api.routes import progress
    sess = tmp_path / "data" / "sessions"
    sess.mkdir(parents=True)
    for i in range(25):
        p = sess / f"z{i:02d}.json"
        p.write_text(json.dumps({"exercise_id": "x", "n": i}), encoding="utf-8")
        os.utime(p, (1000 + i, 1000 + i))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.api.routes.curriculum_exercises", lambda: [])
    recent = asyncio.run(progress())["recent"]
    assert [r["n"] for r in recent] == list(range(24, 4, -1))
