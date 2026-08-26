"""Build a TeacherContext from real MVP-4 objects (bounded, explicit).

This is the ONLY place that translates application state into the limited
slice the LLM sees. Keeping it here means the model can never reach into the
whole app — only what we explicitly project.
"""
from __future__ import annotations

from typing import Optional

from .context import TeacherContext
from perception.performance import PerformanceResult
from perception.skill import SkillState


def build_context(
    student_profile: dict,
    skill_state: Optional[SkillState] = None,
    exercise: Optional[dict] = None,
    performance: Optional[PerformanceResult] = None,
    available_exercises: Optional[list] = None,
    voice_mode: str = "COACH",
) -> TeacherContext:
    current_skill = skill_state.to_dict() if skill_state is not None else None
    latest_performance = performance.to_dict() if performance is not None else None
    return TeacherContext(
        student=student_profile,
        current_skill=current_skill,
        current_exercise=exercise,
        latest_performance=latest_performance,
        available_exercises=available_exercises or [],
        voice_mode=voice_mode,
    )
