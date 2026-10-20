"""Exercise Loader (MVP-3 → CHANGE-06 Schema v2).

Loads the exercise schema from a JSON file (no database yet, per ARCH §21).

CHANGE-05: tempo/BPM is a property of the exercise (the content), not a
hardcoded constant in the runtime. The JSON defines start_bpm, target_bpm and
subdivision; the loader carries them so every consumer reads the tempo from
the exercise definition (single source of truth).

CHANGE-06: Schema v2 — the exercise becomes a richer content contract. New
fields (description, subskill, technique, objective, prerequisites, evaluation,
success_criteria, failure_criteria, common_mistakes, hints, progression) are
defined as CONTENT CONTRACT: loaded, validated, exposed — but no engine
executes them yet. They are the foundation for the future learning system.
Required fields are validated; optional fields are tolerated. No silent
fallback to magic values.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Fields that MUST be present in an exercise JSON (Schema v2).
REQUIRED_FIELDS = ("id", "name", "skill", "difficulty", "target_notes",
                   "start_bpm", "target_bpm", "subdivision")


@dataclass
class Exercise:
    # identity (required first — dataclass ordering: no defaults before required)
    id: str
    name: str
    skill: str
    difficulty: int
    target_notes: List[str]
    # optional identity
    description: Optional[str] = None
    # optional domain
    subskill: Optional[str] = None
    technique: Optional[str] = None
    # tempo (property of the content, CHANGE-05)
    start_bpm: Optional[int] = None
    target_bpm: Optional[int] = None
    subdivision: Optional[str] = None
    # pedagogy (content contract, CHANGE-06 — no engine yet)
    objective: Optional[str] = None
    prerequisites: List[str] = field(default_factory=list)
    evaluation: dict = field(default_factory=dict)
    success_criteria: dict = field(default_factory=dict)
    failure_criteria: dict = field(default_factory=dict)
    common_mistakes: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    progression: dict = field(default_factory=dict)
    # forward-compat
    rules: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def expected_sequence(self) -> List[str]:
        """The note sequence the student should play (MVP-3 target).

        rules.collapse_repeats (songs): the EventTracker merges a re-struck
        identical note without silence, so repeated notes are compared as one.
        """
        notes = list(self.target_notes)
        if self.rules.get("collapse_repeats"):
            notes = [n for i, n in enumerate(notes) if i == 0 or n != notes[i - 1]]
        return notes

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "skill": self.skill,
            "difficulty": self.difficulty,
            "target_notes": list(self.target_notes),
        }
        if self.description is not None:
            d["description"] = self.description
        if self.subskill is not None:
            d["subskill"] = self.subskill
        if self.technique is not None:
            d["technique"] = self.technique
        if self.start_bpm is not None:
            d["start_bpm"] = self.start_bpm
        if self.target_bpm is not None:
            d["target_bpm"] = self.target_bpm
        if self.subdivision is not None:
            d["subdivision"] = self.subdivision
        if self.objective is not None:
            d["objective"] = self.objective
        if self.prerequisites:
            d["prerequisites"] = list(self.prerequisites)
        if self.evaluation:
            d["evaluation"] = self.evaluation
        if self.success_criteria:
            d["success_criteria"] = self.success_criteria
        if self.failure_criteria:
            d["failure_criteria"] = self.failure_criteria
        if self.common_mistakes:
            d["common_mistakes"] = list(self.common_mistakes)
        if self.hints:
            d["hints"] = list(self.hints)
        if self.progression:
            d["progression"] = self.progression
        if self.rules:
            d["rules"] = self.rules
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


def validate_exercise(ex: "Exercise") -> List[str]:
    """Validate a loaded Exercise against the Schema v2 contract.

    Returns a list of problems (empty = valid). Combines required-field checks
    with skill/subskill references. No silent fallback to magic values.
    """
    problems: List[str] = []
    if not ex.id:
        problems.append("exercise id is empty")
    if not ex.name:
        problems.append("exercise name is empty")
    if ex.difficulty < 1:
        problems.append(f"difficulty must be >= 1, got {ex.difficulty}")
    if not ex.target_notes:
        problems.append("target_notes is empty")
    if ex.target_bpm is None:
        problems.append("target_bpm is required (CHANGE-05)")
    if ex.subdivision is None:
        problems.append("subdivision is required (CHANGE-05)")
    # skill/subskill references against the known domain.
    _skill_problems = _validate_skill_reference(ex.skill, ex.subskill)
    problems.extend(_skill_problems)
    return problems


def _validate_skill_reference(skill_id: str, subskill_id: Optional[str]) -> List[str]:
    from .skills import validate_exercise_skill
    return validate_exercise_skill(skill_id, subskill_id)


def _from_dict(data: dict) -> Exercise:
    # Required fields (Schema v2). No silent fallback to magic values.
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"Exercise JSON missing required fields: {missing}")
    # Keep unknown keys for forward-compat, but not required.
    known = set(REQUIRED_FIELDS) | {
        "description", "subskill", "technique", "objective", "prerequisites",
        "evaluation", "success_criteria", "failure_criteria", "common_mistakes",
        "hints", "progression", "rules",
    }
    extra = {k: v for k, v in data.items() if k not in known}
    return Exercise(
        id=data["id"],
        name=data["name"],
        description=data.get("description"),
        skill=data["skill"],
        subskill=data.get("subskill"),
        technique=data.get("technique"),
        difficulty=int(data["difficulty"]),
        target_notes=list(data["target_notes"]),
        start_bpm=data.get("start_bpm"),
        target_bpm=data.get("target_bpm"),
        subdivision=data.get("subdivision"),
        objective=data.get("objective"),
        prerequisites=list(data.get("prerequisites", [])),
        evaluation=data.get("evaluation", {}),
        success_criteria=data.get("success_criteria", {}),
        failure_criteria=data.get("failure_criteria", {}),
        common_mistakes=list(data.get("common_mistakes", [])),
        hints=list(data.get("hints", [])),
        progression=data.get("progression", {}),
        rules=data.get("rules", {}),
        extra=extra,
    )
