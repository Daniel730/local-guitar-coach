"""CHANGE-06 regression tests: Exercise Schema v2 + Skills/Subskills.

Scope: content contract only. No engine executes the new fields yet. Tests
prove: schema v2 loads, required fields validated (no silent fallback), skill/
subskill references validated, existing exercise migrates deterministically,
and runtime consumers (session/teacher) still work.

Out of scope (untouched): perception/, audio_probe/, curriculum, adaptive
learning, Teacher redesign, Progress overhaul, UI, tuner, P2-D/USB.
"""
from __future__ import annotations
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ---- Schema v2: new content fields load ----

def test_schema_v2_loads_new_fields():
    from exercises.exercise import load_exercise
    ex = load_exercise(str(REPO / "exercises" / "scale_e_minor_001.json"))
    # identity
    assert ex.id == "scale_e_minor_001"
    assert ex.name == "E Minor Pentatonic"
    assert ex.description  # new field present
    # domain
    assert ex.skill == "pentatonic"
    assert ex.subskill == "minor_pentatonic"
    assert ex.technique == "alternate_picking"
    # tempo preserved (CHANGE-05)
    assert ex.start_bpm == 60
    assert ex.target_bpm == 100
    assert ex.subdivision == "quarter"
    # pedagogy content contract
    assert ex.objective
    assert ex.prerequisites == []
    assert ex.evaluation
    assert ex.success_criteria
    assert ex.failure_criteria
    assert ex.common_mistakes
    assert ex.hints
    assert ex.progression


def test_schema_v2_to_dict_roundtrip():
    from exercises.exercise import load_exercise, exercise_from_dict
    ex = load_exercise(str(REPO / "exercises" / "scale_e_minor_001.json"))
    d = ex.to_dict()
    ex2 = exercise_from_dict(d)
    assert ex2.id == ex.id
    assert ex2.skill == ex.skill
    assert ex2.subskill == ex.subskill
    assert ex2.target_bpm == ex.target_bpm
    assert ex2.subdivision == ex.subdivision
    assert ex2.objective == ex.objective


# ---- Required fields: no silent fallback ----

def test_required_fields_enforced():
    from exercises.exercise import exercise_from_dict
    # Missing tempo -> must raise (no silent fallback to magic values).
    with pytest.raises(ValueError):
        exercise_from_dict({
            "id": "x", "name": "X", "skill": "pentatonic", "difficulty": 1,
            "target_notes": ["E2"],
        })
    # Missing skill -> must raise.
    with pytest.raises(ValueError):
        exercise_from_dict({
            "id": "x", "name": "X", "difficulty": 1, "target_notes": ["E2"],
            "start_bpm": 60, "target_bpm": 100, "subdivision": "quarter",
        })


# ---- Skill / Subskill validation ----

def test_validate_exercise_valid():
    from exercises.exercise import load_exercise, validate_exercise
    ex = load_exercise(str(REPO / "exercises" / "scale_e_minor_001.json"))
    problems = validate_exercise(ex)
    assert problems == [], f"expected valid, got: {problems}"


def test_validate_exercise_unknown_skill():
    from exercises.exercise import exercise_from_dict, validate_exercise
    ex = exercise_from_dict({
        "id": "x", "name": "X", "skill": "made_up_skill", "difficulty": 1,
        "target_notes": ["E2"], "start_bpm": 60, "target_bpm": 100,
        "subdivision": "quarter",
    })
    problems = validate_exercise(ex)
    assert any("unknown skill" in p for p in problems)


def test_validate_exercise_subskill_mismatch():
    from exercises.exercise import exercise_from_dict, validate_exercise
    # subskill belongs to a different skill -> problem.
    ex = exercise_from_dict({
        "id": "x", "name": "X", "skill": "pentatonic",
        "subskill": "barre_chords",  # belongs to "chords", not "pentatonic"
        "difficulty": 1, "target_notes": ["E2"],
        "start_bpm": 60, "target_bpm": 100, "subdivision": "quarter",
    })
    problems = validate_exercise(ex)
    assert any("does not belong" in p for p in problems)


# ---- Skills domain entities ----

def test_skills_catalog():
    from exercises.skills import get_skill, get_subskill, KNOWN_SKILLS
    assert "pentatonic" in KNOWN_SKILLS
    s = get_skill("pentatonic")
    assert s is not None
    assert "minor_pentatonic" in s.subskills
    sub = get_subskill("minor_pentatonic")
    assert sub is not None
    assert sub.skill_id == "pentatonic"


# ---- Runtime consumers still work (compatibility) ----

def test_session_service_still_works():
    from app.services.session_service import SessionService
    svc = SessionService()
    session = svc.create_session(
        exercise_id="scale_e_minor_001",
        channel=1, sample_rate=44100, block_size=1024, device=1,
    )
    assert session.target_bpm == 100
    assert session.subdivision == "quarter"
    sid = next(iter(svc._sessions))
    svc.stop_session(sid)


def test_teacher_service_still_works():
    from app.services.teacher_service import TeacherService
    svc = TeacherService(exercise_id="scale_e_minor_001", fail_ollama=True)
    assert svc.exercise.skill == "pentatonic"
    assert svc.exercise.subskill == "minor_pentatonic"
    assert svc.exercise.target_bpm == 100
