"""JSON persistence for MVP-4 (no SQLite yet, per project decision).

We are still discovering the data model, so we store PerformanceResult and
SkillState as JSON files under data/sessions/. A later MVP migrates to SQLite
once the schema is stable.

Layout:
    data/sessions/
        <session_id>.json          # one PerformanceResult
        skill_<skill>.json         # accumulated SkillState
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from perception.performance import PerformanceResult
from perception.skill import SkillState, Attempt


def _session_dir() -> Path:
    p = Path("data") / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_performance(result: PerformanceResult, session_id: Optional[str] = None) -> str:
    d = _session_dir()
    sid = session_id or f"{result.exercise_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    path = d / f"{sid}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def save_skill_state(state: SkillState, session_id: Optional[str] = None) -> str:
    d = _session_dir()
    sid = session_id or f"skill_{state.skill}"
    path = d / f"{sid}.json"
    path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_skill_state(skill: str) -> Optional[SkillState]:
    path = _session_dir() / f"skill_{skill}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return _state_from_dict(data)


def _state_from_dict(data: dict) -> SkillState:
    s = SkillState(
        skill=data["skill"],
        level=data.get("level", 0),
        confidence=data.get("confidence", 0.0),
        best_bpm=data.get("best_bpm"),
        stable_bpm=data.get("stable_bpm"),
        note_accuracy=data.get("note_accuracy"),
        timing_accuracy=data.get("timing_accuracy"),
        consistency=data.get("consistency"),
        trend=data.get("trend", "insufficient_data"),
        level_reason=data.get("level_reason", ""),
    )
    s.attempts = [Attempt(**a) for a in data.get("attempts", [])]
    return s
