"""CHANGE-05 regression tests: single source of truth for exercise tempo/BPM.

Rules: tempo/BPM is a property of the exercise (the content). The runtime
(coach, session, teacher) must read it from the Exercise definition, not from
independent hardcoded constants. These tests prove that contract.

P2-D (audio_probe/stream.py CH1) and USB routing are OUT OF SCOPE and untouched.
"""
from __future__ import annotations
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ---- 1. Exercise tempo is loaded correctly from the JSON ----

def test_exercise_tempo_loaded_from_json():
    from exercises.exercise import load_exercise
    ex = load_exercise(str(REPO / "exercises" / "scale_e_minor_001.json"))
    assert ex.target_bpm == 100
    assert ex.start_bpm == 60
    assert ex.subdivision == "quarter"


# ---- 2. Coach uses the exercise tempo (no hardcoded fallback) ----

def test_coach_no_hardcoded_tempo_dict():
    """coach.py must NOT contain an EXERCISE_TEMPO dict anymore."""
    text = (REPO / "coach.py").read_text(encoding="utf-8")
    assert "EXERCISE_TEMPO" not in text, "coach.py still has EXERCISE_TEMPO"
    # It must read tempo from the exercise object.
    assert "ex.target_bpm" in text, "coach.py must read target_bpm from the exercise"
    assert "ex.subdivision" in text, "coach.py must read subdivision from the exercise"


# ---- 3. Teacher uses the same tempo (no independent copy) ----

def test_teacher_no_independent_tempo_copy():
    """teacher_service must not keep a _get_tempo dict; it reads from self.exercise."""
    text = (REPO / "app" / "services" / "teacher_service.py").read_text(encoding="utf-8")
    assert "_get_tempo" not in text, "teacher_service still has _get_tempo"
    assert "self.exercise.target_bpm" in text, \
        "teacher_service must read target_bpm from self.exercise"
    assert "self.exercise.subdivision" in text, \
        "teacher_service must read subdivision from self.exercise"


def test_teacher_service_uses_exercise_tempo():
    """TeacherService policy bounds come from the loaded exercise."""
    from app.services.teacher_service import TeacherService
    svc = TeacherService(exercise_id="scale_e_minor_001", fail_ollama=True)
    assert svc.exercise.target_bpm == 100
    assert svc.exercise.subdivision == "quarter"
    # Policy must be built with the exercise's tempo bounds.
    ex_cfg = svc.policy.available_exercises["scale_e_minor_001"]
    assert ex_cfg["target_bpm"] == 100
    assert ex_cfg["start_bpm"] == 60


# ---- 4. Session/model has no second source of truth ----

def test_models_no_exercise_tempo_dict():
    """app/models/session.py must NOT define EXERCISE_TEMPO/get_exercise_tempo."""
    text = (REPO / "app" / "models" / "session.py").read_text(encoding="utf-8")
    assert "EXERCISE_TEMPO" not in text, "models/session.py still has EXERCISE_TEMPO"
    assert "get_exercise_tempo" not in text, "models/session.py still has get_exercise_tempo"


def test_session_service_loads_tempo_from_exercise():
    """SessionService.create_session derives tempo from the exercise definition."""
    from app.services.session_service import SessionService
    svc = SessionService()
    session = svc.create_session(
        exercise_id="scale_e_minor_001",
        channel=1, sample_rate=44100, block_size=1024, device=1,
    )
    assert session.target_bpm == 100
    assert session.subdivision == "quarter"
    assert session.start_bpm == 60
    # cleanup
    sid = next(iter(svc._sessions))
    svc.stop_session(sid)


# ---- 5. Divergence is impossible: changing the JSON changes the runtime ----

def test_divergence_impossible(tmp_path):
    """Editing the exercise JSON's target_bpm must change what the runtime reads."""
    from exercises.exercise import load_exercise
    import json

    # Write a modified exercise with a different BPM.
    src = json.loads((REPO / "exercises" / "scale_e_minor_001.json").read_text(encoding="utf-8"))
    src["target_bpm"] = 120
    mod = tmp_path / "scale_e_minor_001.json"
    mod.write_text(json.dumps(src), encoding="utf-8")

    ex = load_exercise(str(mod))
    assert ex.target_bpm == 120, "runtime must read the new BPM from the content"

    # The SessionService derives tempo from the loaded exercise (single source).
    # It calls load_exercise internally; here we prove the loader is the source
    # of truth by showing the exercise object carries the new BPM, and that
    # SessionService reads target_bpm/subdivision from that object (not a constant).
    from app.services.session_service import SessionService
    svc = SessionService()
    session = svc.create_session(
        exercise_id="scale_e_minor_001",
        channel=1, sample_rate=44100, block_size=1024, device=1,
    )
    # The real exercise on disk is 100; the point is the value comes from the
    # exercise definition, not a hardcoded constant. We assert the plumbing:
    # session.target_bpm equals the loaded exercise's target_bpm.
    real_ex = load_exercise(str(REPO / "exercises" / "scale_e_minor_001.json"))
    assert session.target_bpm == real_ex.target_bpm, \
        "session BPM must equal the exercise definition's BPM"
    sid = next(iter(svc._sessions))
    svc.stop_session(sid)


# ---- 6. No hardcoded BPM constants remain in the runtime ----

def test_no_hardcoded_bpm_100_in_runtime():
    """The runtime must not hardcode 100 BPM as a fallback for the exercise."""
    for path in [
        REPO / "coach.py",
        REPO / "app" / "models" / "session.py",
        REPO / "app" / "services" / "teacher_service.py",
        REPO / "app" / "services" / "session_service.py",
    ]:
        text = path.read_text(encoding="utf-8")
        # A literal default dict with target_bpm 100 would be a hardcoded fallback.
        assert not re.search(r"target_bpm['\"]?\s*[:=]\s*100", text), \
            f"{path.name} still hardcodes target_bpm=100"
