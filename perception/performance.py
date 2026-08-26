"""Performance Model (MVP-4).

Turns an Alignment (MVP-3) + exercise timing into a PerformanceResult with
FOUR INDEPENDENT dimensions:

    NOTE ACCURACY   - "did I play the right notes?"
    TIMING ACCURACY - "did I play them at the right time?" (raw ms error kept!)
    TEMPO / BPM     - "how fast did I execute?" (performed vs target, not penalized)
    CONSISTENCY     - "can I repeat it?" (individual attempts stored)

NO overall_score. Dimensions stay separate so the future Teacher (MVP-5/Ollama)
can make pedagogical decisions over raw, explainable metrics — not a blended
number that hides which dimension actually failed.

Persistence is JSON under data/sessions/ (no SQLite yet; we are still
discovering the data model). DB migration happens after MVP-4 when the schema
is stable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from perception.sequence import Comparison, CORRECT, WRONG, MISSING, EXTRA, UNCERTAIN

# Tolerance (seconds) for a played note to count as "in time" with its slot.
DEFAULT_TIMING_TOLERANCE_S = 0.15


@dataclass
class PerformanceResult:
    exercise_id: str
    note_accuracy: float
    timing_accuracy: float
    uncertain_ratio: float
    target_bpm: Optional[float]
    performed_bpm: Optional[float]
    tempo_ratio: Optional[float]
    mean_timing_error_ms: float
    consistency: Optional[float] = None
    duration_seconds: Optional[float] = None
    counts: dict = field(default_factory=dict)
    timing_errors_ms: List[float] = field(default_factory=list)
    # raw per-note timing detail (expected vs played), for future analysis
    note_timing: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "exercise_id": self.exercise_id,
            "note_accuracy": round(self.note_accuracy, 3),
            "timing_accuracy": round(self.timing_accuracy, 3),
            "uncertain_ratio": round(self.uncertain_ratio, 3),
            "target_bpm": self.target_bpm,
            "performed_bpm": self.performed_bpm,
            "tempo_ratio": round(self.tempo_ratio, 3) if self.tempo_ratio is not None else None,
            "mean_timing_error_ms": round(self.mean_timing_error_ms, 1),
            "consistency": round(self.consistency, 3) if self.consistency is not None else None,
            "duration_seconds": round(self.duration_seconds, 2) if self.duration_seconds is not None else None,
            "counts": dict(self.counts),
            "timing_errors_ms": [round(x, 1) for x in self.timing_errors_ms],
            "note_timing": self.note_timing,
        }
        return d


def _expected_times(target_bpm: Optional[float], subdivision: str, n_notes: int) -> List[float]:
    """Generate expected start times (s) for each note of the exercise."""
    if target_bpm is None or target_bpm <= 0:
        return []
    beat = 60.0 / target_bpm
    factor = {"quarter": 1.0, "eighth": 0.5, "half": 2.0, "sixteenth": 0.25}.get(
        subdivision.lower(), 1.0
    )
    step = beat * factor
    return [i * step for i in range(n_notes)]


class PerformanceEvaluator:
    def __init__(self, timing_tolerance_s: float = DEFAULT_TIMING_TOLERANCE_S) -> None:
        self.timing_tolerance_s = timing_tolerance_s

    def evaluate(
        self,
        comparison: Comparison,
        target_bpm: Optional[float] = None,
        subdivision: str = "quarter",
        performed_bpm: Optional[float] = None,
    ) -> PerformanceResult:
        align = comparison.alignment
        n_expected = len(comparison.expected)
        counts = {CORRECT: 0, WRONG: 0, MISSING: 0, EXTRA: 0, UNCERTAIN: 0}
        for a in align:
            if a.status in counts:
                counts[a.status] += 1
            else:
                # unexpected status; do not crash
                counts[a.status] = counts.get(a.status, 0) + 1

        correct = counts[CORRECT]
        uncertain = counts[UNCERTAIN]
        note_accuracy = (correct / n_expected) if n_expected else 0.0
        uncertain_ratio = (uncertain / n_expected) if n_expected else 0.0

        # --- Timing ---
        exp_times = _expected_times(target_bpm, subdivision, n_expected)
        timing_errors: List[float] = []
        note_timing: List[dict] = []
        # Pair each ALIGNED expected slot (that was matched to a played note)
        # with its expected time of the same index.
        exp_idx = 0
        for a in align:
            if a.expected is not None:
                et = exp_times[exp_idx] if exp_idx < len(exp_times) else None
                exp_idx += 1
                if a.played is not None and a.played_start is not None and et is not None:
                    err_ms = (a.played_start - et) * 1000.0
                    timing_errors.append(abs(err_ms))
                    in_time = abs(err_ms) / 1000.0 <= self.timing_tolerance_s
                    note_timing.append({
                        "expected": a.expected,
                        "played": a.played,
                        "expected_time": round(et, 3),
                        "played_time": round(a.played_start, 3),
                        "error_ms": round(err_ms, 1),
                        "in_time": in_time,
                    })
        n_timed = len(timing_errors)
        mean_err = (sum(timing_errors) / n_timed) if n_timed else 0.0
        # timing_accuracy = fraction of notes within tolerance
        in_time = sum(1 for e in timing_errors if e / 1000.0 <= self.timing_tolerance_s)
        timing_accuracy = (in_time / n_timed) if n_timed else 0.0

        # --- Tempo / BPM ---
        tempo_ratio = None
        if target_bpm and performed_bpm:
            tempo_ratio = performed_bpm / target_bpm

        # --- Duration ---
        starts = [a.played_start for a in align if a.played_start is not None]
        ends = [a.played_end for a in align if a.played_end is not None]
        duration = (max(ends) - min(starts)) if (starts and ends) else None

        return PerformanceResult(
            exercise_id=comparison.exercise_id,
            note_accuracy=note_accuracy,
            timing_accuracy=timing_accuracy,
            uncertain_ratio=uncertain_ratio,
            target_bpm=target_bpm,
            performed_bpm=performed_bpm,
            tempo_ratio=tempo_ratio,
            mean_timing_error_ms=mean_err,
            duration_seconds=duration,
            counts=counts,
            timing_errors_ms=timing_errors,
            note_timing=note_timing,
        )
