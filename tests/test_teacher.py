"""MVP-5 — Teacher Brain tests. LLM-failure cases are the priority.

We use FakeLLMProvider so safety does NOT depend on Ollama being installed.
Every malicious/random/broken model response must leave the application safe:
schema-invalid -> fallback; policy-invalid -> reject (no execution); provider
down -> deterministic fallback.
"""
import pytest

from ai.teacher import (
    Teacher, TeacherContext, FakeLLMProvider, PolicyValidator,
    validate_action,
)
from ai.teacher.build_context import build_context


def _exercises():
    return {
        "alternate_picking_001": {"start_bpm": 70, "target_bpm": 120, "enabled": True, "prerequisites": []},
        "scale_e_minor_001": {"start_bpm": 60, "target_bpm": 100, "enabled": True, "prerequisites": []},
    }


def _teacher(mode, exercises=None, **kw):
    prov = FakeLLMProvider(mode=mode, exercise_id="alternate_picking_001")
    policy = PolicyValidator(available_exercises=exercises or _exercises())
    return Teacher(provider=prov, policy=policy, **kw)


def _ctx(ex_id="alternate_picking_001"):
    return build_context(
        student_profile={"experience": "beginner", "goals": ["rock"], "practice_minutes": 30},
        exercise={"id": ex_id, "start_bpm": 70, "target_bpm": 120},
        available_exercises=list(_exercises().keys()),
    )


# ---------- GOOD ----------
def test_good_slow_down_accepted():
    t = _teacher("slow_down_95")
    d = t.decide(_ctx())
    assert d.accepted
    assert d.action == "SLOW_DOWN"
    assert d.tempo == 95
    assert d.source == "llm"


# ---------- INVALID JSON ----------
def test_invalid_json_falls_back():
    t = _teacher("garbage")
    d = t.decide(_ctx())
    assert d.accepted
    assert d.source == "fallback"
    assert d.action == "REPEAT"


# ---------- INVALID ACTION ENUM ----------
def test_invalid_action_rejected():
    t = _teacher("teleport")
    d = t.decide(_ctx())
    # schema invalid -> fallback (safe), never executes TELEPORT
    assert d.source == "fallback"
    assert d.action != "TELEPORT_PLAYER"


# ---------- INVALID BPM (policy) ----------
def test_invalid_bpm_rejected():
    # SPEED_UP 300 is schema-valid but BPM 300 > target 120 -> policy reject
    t = _teacher("speed_up_300")
    d = t.decide(_ctx())
    assert not d.accepted
    assert d.source == "policy_fail"
    assert "BPM" in d.reason


# ---------- INVALID EXERCISE ----------
def test_invalid_exercise_rejected():
    t = _teacher("made_up_ex")
    d = t.decide(_ctx())
    assert not d.accepted
    assert d.source == "policy_fail"
    assert "EXERCISE" in d.reason


# ---------- OLLAMA UNAVAILABLE ----------
def test_ollama_unavailable_fallback():
    t = _teacher("unavailable")
    d = t.decide(_ctx())
    assert d.accepted
    assert d.source == "fallback"
    assert d.action == "REPEAT"


# ---------- MISSING DATA -> EXPLAIN, not invent ----------
def test_missing_data_explain():
    t = _teacher("explain")
    d = t.decide(_ctx())
    # EXPLAIN is a valid action; schema accepts it. Policy allows (non-exercise).
    assert d.accepted
    assert d.action == "EXPLAIN"


# ---------- POLICY: BPM below minimum ----------
def test_bpm_below_minimum_rejected():
    from ai.teacher.policy import REASON_BPM_TOO_LOW
    pol = PolicyValidator(available_exercises=_exercises())
    v = pol.validate("SLOW_DOWN", "alternate_picking_001", tempo=50)  # < start 70
    assert not v.allowed
    assert v.reason == REASON_BPM_TOO_LOW


def test_bpm_above_maximum_rejected():
    from ai.teacher.policy import REASON_BPM_TOO_HIGH
    pol = PolicyValidator(available_exercises=_exercises())
    v = pol.validate("SPEED_UP", "alternate_picking_001", tempo=200)  # > target 120
    assert not v.allowed
    assert v.reason == REASON_BPM_TOO_HIGH


# ---------- SCHEMA UNIT ----------
def test_schema_rejects_unknown_field():
    ok, _, err = validate_action('{"action": "REPEAT", "hack": 1}')
    assert not ok
    assert "unknown field" in err


def test_schema_rejects_bad_action():
    ok, _, err = validate_action('{"action": "FLY_TO_MOON"}')
    assert not ok
    assert "invalid action" in err


def test_schema_requires_action():
    ok, _, err = validate_action('{"tempo": 90}')
    assert not ok
    assert "missing required" in err


def test_schema_unwraps_markdown_fence_only():
    ok, data, _ = validate_action('```json\n{"action": "REPEAT"}\n```')
    assert ok and data["action"] == "REPEAT"
    ok, _, err = validate_action('```json\n{"action": "REPEAT", "hack": 1}\n```')
    assert not ok and "unknown field" in err


# ---------- CONTEXTUAL CONVERSATION ----------
def test_conversation_resolves_current():
    # "Isso está certo?" with no real LLM -> fallback still safe.
    t = _teacher("garbage")
    ctx = _ctx()
    ctx.current_exercise = {"id": "scale_e_minor_001", "name": "E Minor Pentatonic"}
    ctx.latest_performance = {"note_accuracy": 0.94, "timing_accuracy": 0.71}
    d = t.answer(ctx, "Isso está certo?")
    # Must not crash; safe fallback or a valid ANSWER/EXPLAIN.
    assert d.accepted
    assert d.action in ("REPEAT", "ANSWER", "EXPLAIN")


# ---------- E2E: PerformanceResult -> Context -> Teacher -> Action -> Validation ----------
def test_e2e_pipeline():
    from perception.events import NoteEvent
    from perception.sequence import compare
    from perception.performance import PerformanceEvaluator
    from perception.skill import SkillState, SkillStateTracker
    from perception.persistence import save_performance, save_skill_state

    ev = lambda n, s: NoteEvent(n, None, s, s + 0.2, 0.2, 0.9, 0.9)
    exp = ["E2", "G2", "A2", "B2", "D3", "E3"]
    played = [ev(n, i * 0.75) for i, n in enumerate(exp)]
    c = compare("scale_e_minor_001", exp, played)
    perf = PerformanceEvaluator().evaluate(c, target_bpm=80, subdivision="quarter", performed_bpm=80)

    tracker = SkillStateTracker("pentatonic")
    skill = SkillState(skill="pentatonic")
    tracker.update(skill, perf, target_bpm=80)
    save_performance(perf)
    save_skill_state(skill)

    ctx = build_context(
        student_profile={"experience": "beginner", "goals": ["rock"], "practice_minutes": 30},
        skill_state=skill,
        exercise={"id": "scale_e_minor_001", "start_bpm": 60, "target_bpm": 100},
        performance=perf,
        available_exercises=["scale_e_minor_001", "alternate_picking_001"],
    )
    t = _teacher("slow_down_95", exercises=_exercises())
    d = t.decide(ctx)
    assert d.accepted
    assert d.action == "SLOW_DOWN"
    assert d.source == "llm"
