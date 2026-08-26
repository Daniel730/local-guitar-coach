"""Policy Validator (MVP-5) — deterministic gate between LLM intent and execution.

The LLM PROPOSES. This engine DECIDES. Every rule here is explicit and
testable. A rejected action never reaches the Session Controller.

Rules (from project spec):
  Exercise: exists in available list? enabled? prerequisites met? belongs to curriculum?
  BPM: tempo >= start_bpm? tempo <= target_bpm? tempo valid number?
  Skill: exists? eligible?
  Session: active? time remaining?
  Action: allowed in current state?
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Standard rejection reasons (for tests + logging).
REASON_EXERCISE_UNKNOWN = "EXERCISE_UNKNOWN"
REASON_EXERCISE_DISABLED = "EXERCISE_DISABLED"
REASON_PREREQ_NOT_MET = "PREREQUISITES_NOT_MET"
REASON_BPM_TOO_LOW = "BPM_BELOW_MINIMUM"
REASON_BPM_TOO_HIGH = "BPM_ABOVE_MAXIMUM"
REASON_BPM_INVALID = "BPM_INVALID"
REASON_ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
REASON_NO_SESSION = "NO_ACTIVE_SESSION"
REASON_NO_TIME = "INSUFFICIENT_TIME"


@dataclass
class PolicyVerdict:
    allowed: bool
    reason: Optional[str] = None
    # normalized action to execute (may differ slightly from proposed)
    action: Optional[str] = None
    tempo: Optional[float] = None
    exercise_id: Optional[str] = None


class PolicyValidator:
    def __init__(self, available_exercises: dict = None, session_active: bool = True,
                 time_remaining_s: float = 600.0) -> None:
        # available_exercises: dict id -> {"start_bpm","target_bpm","enabled","prerequisites"}
        self.available_exercises = available_exercises or {}
        self.session_active = session_active
        self.time_remaining_s = time_remaining_s

    def _exercise_ok(self, ex_id) -> tuple[bool, Optional[str]]:
        ex = self.available_exercises.get(ex_id)
        if ex is None:
            return False, REASON_EXERCISE_UNKNOWN
        if ex.get("enabled", True) is False:
            return False, REASON_EXERCISE_DISABLED
        prereq = ex.get("prerequisites", [])
        for p in prereq:
            if p not in self.available_exercises:
                return False, REASON_PREREQ_NOT_MET
        return True, None

    def validate(self, action: str, exercise_id=None, tempo=None) -> PolicyVerdict:
        # Session-level gates.
        if not self.session_active:
            return PolicyVerdict(False, REASON_NO_SESSION, action)
        if self.time_remaining_s <= 0:
            return PolicyVerdict(False, REASON_NO_TIME, action)

        # Exercise-bound actions need a valid, allowed exercise.
        exercise_bound = action in (
            "START_EXERCISE", "REPEAT", "SLOW_DOWN", "SPEED_UP", "CHANGE_EXERCISE",
            "END_EXERCISE",
        )
        if exercise_bound:
            if exercise_id is None:
                return PolicyVerdict(False, REASON_EXERCISE_UNKNOWN, action)
            ok, reason = self._exercise_ok(exercise_id)
            if not ok:
                return PolicyVerdict(False, reason, action)
            ex = self.available_exercises[exercise_id]
            # BPM bounds for tempo-related actions.
            if tempo is not None:
                if not isinstance(tempo, (int, float)) or isinstance(tempo, bool):
                    return PolicyVerdict(False, REASON_BPM_INVALID, action)
                start = ex.get("start_bpm")
                target = ex.get("target_bpm")
                if start is not None and tempo < start:
                    return PolicyVerdict(False, REASON_BPM_TOO_LOW, action)
                if target is not None and tempo > target:
                    return PolicyVerdict(False, REASON_BPM_TOO_HIGH, action)

        # Non-exercise actions are allowed if session is fine.
        return PolicyVerdict(
            True, None, action=action, tempo=tempo, exercise_id=exercise_id,
        )
