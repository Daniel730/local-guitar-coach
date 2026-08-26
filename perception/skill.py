"""Student Skill State (MVP-4).

Aggregates multiple PerformanceResults into a SkillState. Key design rules
(from project decision 2026-08-26):

* NO overall score anywhere.
* `level` is DERIVED FROM EXPLICIT PEDAGOGICAL CRITERIA, not a mean of scores.
* `consistency` and `stable_bpm` come from individual attempts (outliers do
  not redefine the student).
* `trend` needs MULTIPLE observations; one bad session is not "declining".
* `confidence` reflects how much evidence we have, independent of `level`.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional

from perception.performance import PerformanceResult


# Pedagogical level thresholds, explicit and explainable.
# A higher level requires tighter criteria across dimensions.
LEVEL_CRITERIA = [
    # level 3: demanding
    {"level": 3, "min_note_accuracy": 0.92, "min_timing_accuracy": 0.88,
     "min_stable_bpm_factor": 1.0},  # stable_bpm >= target * factor (set per call)
    # level 2
    {"level": 2, "min_note_accuracy": 0.90, "min_timing_accuracy": 0.80,
     "min_stable_bpm_factor": 0.0},
    # level 1
    {"level": 1, "min_note_accuracy": 0.85, "min_timing_accuracy": 0.0,
     "min_stable_bpm_factor": 0.0},
]


@dataclass
class Attempt:
    exercise_id: str
    note_accuracy: float
    timing_accuracy: float
    performed_bpm: Optional[float]
    target_bpm: Optional[float]
    mean_timing_error_ms: float
    duration_seconds: Optional[float]
    counts: dict = field(default_factory=dict)

    @classmethod
    def from_result(cls, r: PerformanceResult) -> "Attempt":
        return cls(
            exercise_id=r.exercise_id,
            note_accuracy=r.note_accuracy,
            timing_accuracy=r.timing_accuracy,
            performed_bpm=r.performed_bpm,
            target_bpm=r.target_bpm,
            mean_timing_error_ms=r.mean_timing_error_ms,
            duration_seconds=r.duration_seconds,
            counts=dict(r.counts),
        )

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "note_accuracy": round(self.note_accuracy, 3),
            "timing_accuracy": round(self.timing_accuracy, 3),
            "performed_bpm": self.performed_bpm,
            "target_bpm": self.target_bpm,
            "mean_timing_error_ms": round(self.mean_timing_error_ms, 1),
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "counts": dict(self.counts),
        }


@dataclass
class SkillState:
    skill: str
    level: int = 0
    confidence: float = 0.0
    best_bpm: Optional[float] = None
    stable_bpm: Optional[float] = None
    note_accuracy: Optional[float] = None
    timing_accuracy: Optional[float] = None
    consistency: Optional[float] = None
    trend: str = "insufficient_data"
    attempts: List[Attempt] = field(default_factory=list)
    # pedagogical explanation of current level
    level_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "level": self.level,
            "confidence": round(self.confidence, 3),
            "best_bpm": self.best_bpm,
            "stable_bpm": self.stable_bpm,
            "note_accuracy": round(self.note_accuracy, 3) if self.note_accuracy is not None else None,
            "timing_accuracy": round(self.timing_accuracy, 3) if self.timing_accuracy is not None else None,
            "consistency": round(self.consistency, 3) if self.consistency is not None else None,
            "trend": self.trend,
            "level_reason": self.level_reason,
            "attempts": [a.to_dict() for a in self.attempts],
        }


class SkillStateTracker:
    """Builds/updates a SkillState from attempts.

    Stability rule: stable_bpm is the MEDIAN of performed BPMs, not the max,
    so a single hot run (140) does not redefine the student whose stable
    speed is ~100. best_bpm is the max (the ceiling they have reached).
    """

    def __init__(self, skill: str) -> None:
        self.skill = skill

    def update(self, state: SkillState, result: PerformanceResult, target_bpm: Optional[float] = None) -> SkillState:
        state.attempts.append(Attempt.from_result(result))
        self._recompute(state, target_bpm)
        return state

    def _recompute(self, state: SkillState, target_bpm: Optional[float]) -> None:
        attempts = state.attempts
        n = len(attempts)
        if n == 0:
            return

        # Dimensions = mean across attempts (observation, not a "score").
        state.note_accuracy = statistics.fmean(a.note_accuracy for a in attempts)
        state.timing_accuracy = statistics.fmean(a.timing_accuracy for a in attempts)

        bpms = [a.performed_bpm for a in attempts if a.performed_bpm is not None]
        if bpms:
            state.best_bpm = max(bpms)
            # stable = median (robust to a single outlier run)
            state.stable_bpm = round(statistics.median(bpms), 1)
        else:
            state.best_bpm = None
            state.stable_bpm = None

        # Consistency: how tight are the note-accuracy results across attempts.
        # 1.0 = identical every time; lower = erratic.
        if n >= 2:
            sd = statistics.pstdev(a.note_accuracy for a in attempts)
            # map sd -> 0..1 (sd 0 -> 1, sd >= 0.2 -> 0)
            state.consistency = max(0.0, min(1.0, 1.0 - sd / 0.2))
        else:
            state.consistency = None

        # Confidence: grows with number of observations (independent of level).
        state.confidence = min(1.0, n / 5.0)

        # Level from explicit pedagogical criteria.
        state.level, state.level_reason = self._derive_level(
            state.note_accuracy, state.timing_accuracy, state.stable_bpm, target_bpm
        )

        # Trend: requires multiple observations.
        state.trend = self._derive_trend(attempts)

    def _derive_level(self, note_acc, timing_acc, stable_bpm, target_bpm) -> tuple[int, str]:
        for crit in LEVEL_CRITERIA:
            ok = note_acc >= crit["min_note_accuracy"]
            if crit["min_timing_accuracy"] > 0:
                ok = ok and timing_acc >= crit["min_timing_accuracy"]
            if crit["min_stable_bpm_factor"] > 0 and target_bpm and stable_bpm is not None:
                ok = ok and stable_bpm >= target_bpm * crit["min_stable_bpm_factor"]
            if ok:
                reason = (
                    f"note_accuracy>={crit['min_note_accuracy']:.2f}"
                    + (f", timing>={crit['min_timing_accuracy']:.2f}" if crit["min_timing_accuracy"] > 0 else "")
                    + (f", stable_bpm>={target_bpm * crit['min_stable_bpm_factor']:.0f}" if (crit['min_stable_bpm_factor'] > 0 and target_bpm) else "")
                )
                return crit["level"], reason
        return 0, "below level 1 thresholds"

    def _derive_trend(self, attempts: List[Attempt]) -> str:
        n = len(attempts)
        if n < 3:
            return "insufficient_data"
        # Use last 3 attempts (most recent window).
        window = attempts[-3:]
        accs = [a.note_accuracy for a in window]
        # Require the direction to be consistent across the window.
        deltas = [accs[i + 1] - accs[i] for i in range(len(accs) - 1)]
        if all(d > 0.02 for d in deltas):
            return "improving"
        if all(d < -0.02 for d in deltas):
            return "declining"
        # mixed or flat
        if max(accs) - min(accs) < 0.03:
            return "stable"
        return "stable"  # noisy single-session dip is NOT "declining"
