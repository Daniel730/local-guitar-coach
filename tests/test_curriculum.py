"""Curriculum: deterministic mastery + progression, and GET /api/next."""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi import HTTPException

from exercises.curriculum import (
    is_mastered, list_exercises, load_attempts, next_exercise, record_attempt,
)
from exercises.exercise import exercise_from_dict


def _ex(ex_id, difficulty=1, prereq=(), **crit):
    return exercise_from_dict({
        "id": ex_id, "name": ex_id, "skill": "pentatonic", "difficulty": difficulty,
        "target_notes": ["E2", "G2"], "start_bpm": 60, "target_bpm": 100,
        "subdivision": "quarter", "prerequisites": list(prereq),
        "success_criteria": crit or {"min_note_accuracy": 0.9, "min_timing_accuracy": 0.8},
    })


def _att(ex_id, note=1.0, timing=1.0, bpm=100):
    return {"exercise_id": ex_id, "note_accuracy": note, "timing_accuracy": timing,
            "target_bpm": 100, "performed_bpm": bpm}


GOOD = dict(note=0.95, timing=0.9)
BAD = dict(note=0.6, timing=0.9)


def test_not_enough_attempts():
    a = _ex("a")
    assert not is_mastered(a, [])
    assert not is_mastered(a, [_att("a", **GOOD)])
    r = next_exercise("a", [a], [_att("a", **GOOD)])
    assert r == {"current": "a", "mastered": False, "next_exercise_id": "a",
                 "reason": r["reason"]}
    assert "insuficientes" in r["reason"]


def test_two_of_last_three():
    a = _ex("a")
    assert is_mastered(a, [_att("a", **GOOD), _att("a", **BAD), _att("a", **GOOD)])
    # Only the last 3 count: old successes don't help.
    hist = [_att("a", **GOOD)] * 3 + [_att("a", **BAD), _att("a", **BAD), _att("a", **GOOD)]
    assert not is_mastered(a, hist)
    r = next_exercise("a", [a], hist)
    assert r["mastered"] is False and r["next_exercise_id"] == "a"
    assert "1 de 3" in r["reason"] and "0.90" in r["reason"]
    # Other exercises' attempts are ignored.
    assert not is_mastered(a, [_att("b", **GOOD)] * 3)


def test_bpm_factor_and_missing_keys_ignored():
    a = _ex("a", min_note_accuracy=0.9, min_bpm_factor=0.8)
    assert not is_mastered(a, [_att("a", note=1, timing=0.0, bpm=70)] * 3)
    assert is_mastered(a, [_att("a", note=1, timing=0.0, bpm=80)] * 2)


def test_prerequisite_gating():
    a, b, c = _ex("a", 1), _ex("b", 2, prereq=["z_hard"]), _ex("c", 3, prereq=["a"])
    z = _ex("z_hard", 1)
    exercises = [a, b, c, z]
    att = [_att("a", **GOOD)] * 2
    r = next_exercise("a", exercises, att)
    # z_hard (diff 1, no prereq) comes before b (prereq unmet) and c.
    assert r == {"current": "a", "mastered": True, "next_exercise_id": "z_hard",
                 "reason": r["reason"]}
    att += [_att("z_hard", **GOOD)] * 2
    assert next_exercise("a", exercises, att)["next_exercise_id"] == "b"


def test_everything_done():
    a, b = _ex("a", 1), _ex("b", 2, prereq=["a"])
    att = [_att("a", **GOOD)] * 2 + [_att("b", **GOOD)] * 2
    r = next_exercise("b", [a, b], att)
    assert r["mastered"] is True and r["next_exercise_id"] is None


def test_unknown_current_raises():
    with pytest.raises(KeyError):
        next_exercise("nope", [_ex("a")], [])


def _write_curriculum(tmp_path):
    ex_dir = tmp_path / "exercises"
    ex_dir.mkdir()
    for e in (_ex("b_two", 2, prereq=["a_one"]), _ex("a_one", 1)):
        (ex_dir / f"{e.id}.json").write_text(json.dumps(e.to_dict()), encoding="utf-8")
    (ex_dir / "broken.json").write_text("{}", encoding="utf-8")
    sess = tmp_path / "data" / "sessions"
    sess.mkdir(parents=True)
    return ex_dir, sess


def test_list_and_load_attempts(tmp_path):
    ex_dir, sess = _write_curriculum(tmp_path)
    assert [e.id for e in list_exercises(str(ex_dir))] == ["a_one", "b_two"]
    for i, name in enumerate(["x2", "x1"]):
        p = sess / f"{name}.json"
        p.write_text(json.dumps(_att("a_one", note=i)), encoding="utf-8")
        os.utime(p, (1000 + i, 1000 + i))
    (sess / "skill_pentatonic.json").write_text(json.dumps({"skill": "p"}), encoding="utf-8")
    (sess / "other.json").write_text(json.dumps({"foo": 1}), encoding="utf-8")
    att = load_attempts(sess)
    assert [a["note_accuracy"] for a in att] == [0, 1]  # legacy files imported in mtime order
    record_attempt(_att("a_one", note=2), sess)
    assert [a["note_accuracy"] for a in load_attempts(sess)] == [0, 1, 2]


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    _, sess = _write_curriculum(tmp_path)
    monkeypatch.chdir(tmp_path)
    import perception.persistence as persistence
    monkeypatch.setattr(persistence, "_session_dir", lambda: sess)
    return sess


def test_api_next_direct(api_env):
    from app.api.routes import next_step
    r = asyncio.run(next_step(current="a_one"))
    assert set(r) == {"current", "mastered", "next_exercise_id", "reason"}
    assert r["next_exercise_id"] == "a_one" and r["mastered"] is False
    for i in range(2):
        record_attempt(_att("a_one", **GOOD), api_env)
    r = asyncio.run(next_step(current="a_one"))
    assert r["mastered"] is True and r["next_exercise_id"] == "b_two"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(next_step(current="nope"))
    assert exc.value.status_code == 404


def test_api_next_http(api_env):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routes import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/next", params={"current": "a_one"})
    assert r.status_code == 200
    assert r.json()["next_exercise_id"] == "a_one"
    assert client.get("/api/next", params={"current": "nope"}).status_code == 404


def test_api_progress_by_exercise(api_env):
    from app.api.routes import progress
    assert asyncio.run(progress())["by_exercise"] == {}
    for i in range(2):
        record_attempt(_att("a_one", **GOOD), api_env)
    p = asyncio.run(progress())
    a = p["by_exercise"]["a_one"]
    assert a["attempts"] == 2 and a["mastered"] is True and len(a["history"]) == 2
    assert set(a["history"][0]) == {"note_accuracy", "timing_accuracy", "performed_bpm"}
    assert "b_two" not in p["by_exercise"]
    assert p["skill_names"]["pentatonic"]
