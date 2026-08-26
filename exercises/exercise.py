"""Exercise Loader (MVP-3).

Loads the exercise schema from a JSON file (no database yet, per ARCH §21).
Schema (ARCH §7):
    {
      "id": "scale_e_minor_001",
      "name": "E Minor Pentatonic",
      "skill": "pentatonic",
      "difficulty": 1,
      "target_notes": ["E2","G2","A2","B2","D3","E3"]
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Exercise:
    id: str
    name: str
    skill: str
    difficulty: int
    target_notes: List[str]
    # optional fields tolerated but not required yet
    start_bpm: Optional[int] = None
    target_bpm: Optional[int] = None
    rules: dict = field(default_factory=dict)
    progression: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def expected_sequence(self) -> List[str]:
        """The note sequence the student should play (MVP-3 target)."""
        return list(self.target_notes)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "skill": self.skill,
            "difficulty": self.difficulty,
            "target_notes": list(self.target_notes),
        }
        if self.start_bpm is not None:
            d["start_bpm"] = self.start_bpm
        if self.target_bpm is not None:
            d["target_bpm"] = self.target_bpm
        if self.rules:
            d["rules"] = self.rules
        if self.progression:
            d["progression"] = self.progression
        d.update(self.extra)
        return d


def load_exercise(path) -> Exercise:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Exercise file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return _from_dict(data)


def exercise_from_dict(data: dict) -> Exercise:
    return _from_dict(data)


def _from_dict(data: dict) -> Exercise:
    if "id" not in data or "target_notes" not in data:
        raise ValueError("Exercise JSON must contain 'id' and 'target_notes'")
    # Keep unknown keys for forward-compat, but not required.
    known = {"id", "name", "skill", "difficulty", "target_notes",
             "start_bpm", "target_bpm", "rules", "progression"}
    extra = {k: v for k, v in data.items() if k not in known}
    return Exercise(
        id=data["id"],
        name=data.get("name", data["id"]),
        skill=data.get("skill", "unknown"),
        difficulty=int(data.get("difficulty", 1)),
        target_notes=list(data["target_notes"]),
        start_bpm=data.get("start_bpm"),
        target_bpm=data.get("target_bpm"),
        rules=data.get("rules", {}),
        progression=data.get("progression", {}),
        extra=extra,
    )
