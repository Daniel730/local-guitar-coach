"""TeacherContext (MVP-5).

The explicit, bounded slice of application state the LLM is allowed to see.
This is NOT a dump of the whole app — it is a structured, minimal context so
the model reasons from data we actually have, and cannot invent the rest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeacherContext:
    student: dict = field(default_factory=dict)
    current_skill: Optional[dict] = None
    current_exercise: Optional[dict] = None
    latest_performance: Optional[dict] = None
    # exercises the model is allowed to reference (ids only)
    available_exercises: list = field(default_factory=list)
    voice_mode: str = "COACH"
    # pre-rendered textual context (set by Teacher.build_context)
    rendered: str = ""

    def to_dict(self) -> dict:
        return {
            "student": self.student,
            "current_skill": self.current_skill,
            "current_exercise": self.current_exercise,
            "latest_performance": self.latest_performance,
            "available_exercises": list(self.available_exercises),
            "voice_mode": self.voice_mode,
        }
