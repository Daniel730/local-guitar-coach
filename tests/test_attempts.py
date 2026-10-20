"""MVP-7 v1: one teacher decision per ATTEMPT (not per timer tick)."""
import time

from app.services.session_service import SessionService
from app.services.teacher_service import TeacherService
from perception.events import NoteEvent
from perception.notes import note_to_midi

TARGET = ["E2", "G2", "A2", "B2", "D3", "E3"]  # scale_e_minor_001


def _ne(note, start):
    return NoteEvent(note=note, midi=note_to_midi(note), start=start, end=start + 0.5,
                     duration=0.5, confidence=0.95, attack_confidence=0.9)


def _teacher():
    return TeacherService(exercise_id="scale_e_minor_001", fail_ollama=True,
                          attempt_silence_s=2.5)


def test_no_attempt_without_notes():
    assert not _teacher().attempt_ready()


def test_attempt_ready_when_all_notes_played():
    t = _teacher()
    for i, n in enumerate(TARGET):
        assert not t.attempt_ready()
        t.add_note_event(_ne(n, i * 0.6))
    assert t.attempt_ready()


def test_attempt_ready_after_silence():
    t = _teacher()
    t.add_note_event(_ne("E2", 0.0))
    now = time.monotonic()
    assert not t.attempt_ready(now=now + 1.0)
    assert t.attempt_ready(now=now + 3.0)


def test_close_attempt_decides_once_and_clears_buffer():
    t = _teacher()
    for i, n in enumerate(TARGET):
        t.add_note_event(_ne(n, i * 0.6))
    decision = t.close_attempt()
    assert decision.source == "fallback"          # Ollama forced unavailable
    assert t.attempt_count == 1
    assert not t.has_pending_notes()
    assert not t.attempt_ready()
    assert t._performance.note_accuracy == 1.0


def _service_with_session(tmp_path, monkeypatch):
    monkeypatch.setattr("perception.persistence._session_dir", lambda: tmp_path)
    svc = SessionService()
    session = svc.create_session(exercise_id="scale_e_minor_001", channel=1,
                                 sample_rate=44100, block_size=1024, device=0)
    sid = session.session_id
    assert sid and svc.get_session(sid) is session
    svc._teacher_services[sid] = _teacher()
    return svc, sid


def test_session_close_attempt_emits_result_and_teacher(tmp_path, monkeypatch):
    svc, sid = _service_with_session(tmp_path, monkeypatch)
    teacher = svc.get_teacher_service(sid)
    for i, n in enumerate(TARGET):
        teacher.add_note_event(_ne(n, i * 0.6))
    msgs = svc.close_attempt(sid)
    types = [m["type"] for m in msgs]
    assert types == ["attempt_result", "teacher"]
    result = msgs[0]
    assert result["attempt"] == 1
    assert result["performance"]["note_accuracy"] == 1.0
    assert "overall_score" not in result["performance"]   # 4 dims, never a score
    assert result["skill"]["skill"] == "pentatonic"
    assert (tmp_path / f"{sid}_a1.json").exists()
    # A second persist of the same attempt is a no-op.
    assert svc.persist_session(sid) is None


def test_stop_evaluates_unfinished_attempt_without_teacher(tmp_path, monkeypatch):
    svc, sid = _service_with_session(tmp_path, monkeypatch)
    teacher = svc.get_teacher_service(sid)
    for i, n in enumerate(TARGET[:3]):          # half the notes: still an attempt
        teacher.add_note_event(_ne(n, i * 0.6))
    assert svc.stop_session(sid)
    assert teacher._last_decision is None      # no LLM call on stop
    assert (tmp_path / f"{sid}_a1.json").exists()


def test_stray_note_does_not_close_attempt_early():
    t = _teacher()
    for i, n in enumerate(["E2", "G2", "G#2", "A2", "B2", "D3"]):  # slip, E3 not yet played
        t.add_note_event(_ne(n, i * 0.6))
    assert not t.attempt_ready(now=time.monotonic())
    t.add_note_event(_ne("E3", 4.2))
    assert t.attempt_ready()


def test_too_short_attempt_is_discarded(tmp_path, monkeypatch):
    svc, sid = _service_with_session(tmp_path, monkeypatch)
    teacher = svc.get_teacher_service(sid)
    teacher.add_note_event(_ne("E2", 0.0))     # testing the sound
    assert svc.close_attempt(sid) == []
    assert teacher.attempt_count == 0 and not teacher.has_pending_notes()
    assert not list(tmp_path.glob("*.json"))


def test_song_attempt_counts_collapsed_notes():
    t = TeacherService(exercise_id="song_twinkle_a", fail_ollama=True)
    melody = "C3 C3 G3 G3 A3 A3 G3 F3 F3 E3 E3 D3 D3 C3".split()
    for i, n in enumerate(melody[:8]):        # re-strikes arrive as separate events
        t.add_note_event(_ne(n, i * 0.6))
    assert not t.attempt_ready(now=time.monotonic())
    for i, n in enumerate(melody[8:], start=8):
        t.add_note_event(_ne(n, i * 0.6))
    assert t.attempt_ready()
    t.close_attempt()
    assert t._performance.note_accuracy == 1.0
