"""Curriculum — deterministic exercise progression.

The system decides progression from persisted performance data; the Teacher
(LLM) only recommends (PROJECT_STATE §7.7). Dimensions stay separate: mastery
checks each success criterion independently, never an overall score (§7.6).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Optional

from exercises.exercise import Exercise, load_exercise

logger = logging.getLogger(__name__)

MASTERY_WINDOW = 3     # look at the last N attempts
MASTERY_REQUIRED = 2   # of which at least this many must meet the criteria


def list_exercises(dir: str = "exercises") -> List[Exercise]:
    """Load every exercises/*.json, sorted by (difficulty, id). Invalid files are skipped."""
    out: List[Exercise] = []
    for path in sorted(Path(dir).glob("*.json")):
        try:
            out.append(load_exercise(path))
        except Exception as exc:  # malformed exercise must not break the curriculum
            logger.warning("Skipping invalid exercise %s: %s", path, exc)
    return sorted(out, key=lambda e: (e.difficulty, e.id))


def load_attempts(session_dir=None) -> List[dict]:
    """Per-attempt performance dicts from the persistence dir, ordered by file mtime."""
    if session_dir is None:
        from perception import persistence
        session_dir = persistence._session_dir()
    d = Path(session_dir)
    if not d.is_dir():
        return []
    attempts = []
    for path in sorted(d.glob("*.json"), key=lambda p: (p.stat().st_mtime, p.name)):
        if path.name.startswith("skill_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("exercise_id"):
            attempts.append(data)
    return attempts


def _attempts_for(exercise_id: str, attempts: Iterable[dict]) -> List[dict]:
    return [a for a in attempts if a.get("exercise_id") == exercise_id]


def _criteria_failures(exercise: Exercise, attempt: dict) -> List[str]:
    """List of human-readable unmet criteria for one attempt (empty = met)."""
    crit = exercise.success_criteria or {}
    fails: List[str] = []
    if "min_note_accuracy" in crit:
        v = attempt.get("note_accuracy")
        if v is None or v < crit["min_note_accuracy"]:
            fails.append(f"notas {_fmt(v)} (mín {crit['min_note_accuracy']:.2f})")
    if "min_timing_accuracy" in crit:
        v = attempt.get("timing_accuracy")
        if v is None or v < crit["min_timing_accuracy"]:
            fails.append(f"timing {_fmt(v)} (mín {crit['min_timing_accuracy']:.2f})")
    if "min_bpm_factor" in crit and exercise.target_bpm:
        need = exercise.target_bpm * crit["min_bpm_factor"]
        v = attempt.get("performed_bpm")
        if v is None or v < need:
            fails.append(f"BPM {_fmt(v, 0)} (mín {need:.0f})")
    return fails


def _fmt(v, digits: int = 2) -> str:
    return "n/d" if v is None else f"{v:.{digits}f}"


def attempt_meets(exercise: Exercise, attempt: dict) -> bool:
    return not _criteria_failures(exercise, attempt)


def is_mastered(exercise: Exercise, attempts: List[dict]) -> bool:
    """>= 2 of the last 3 attempts of this exercise meet its success_criteria."""
    mine = _attempts_for(exercise.id, attempts)[-MASTERY_WINDOW:]
    if len(mine) < MASTERY_REQUIRED:
        return False
    return sum(attempt_meets(exercise, a) for a in mine) >= MASTERY_REQUIRED


def _missing_reason(exercise: Exercise, attempts: List[dict]) -> str:
    mine = _attempts_for(exercise.id, attempts)[-MASTERY_WINDOW:]
    if len(mine) < MASTERY_REQUIRED:
        return (f"Tentativas insuficientes: {len(mine)} de {MASTERY_REQUIRED} "
                f"necessárias para avaliar domínio.")
    met = sum(attempt_meets(exercise, a) for a in mine)
    fails = next((f for f in (_criteria_failures(exercise, a) for a in reversed(mine)) if f), [])
    return (f"Ainda não dominado: {met} de {len(mine)} últimas tentativas atingiram "
            f"o critério (precisa {MASTERY_REQUIRED}). Falta: {'; '.join(fails)}.")


def next_exercise(current_id: str, exercises: List[Exercise], attempts: List[dict]) -> dict:
    """Deterministic next step: repeat until mastered, then first unlocked unmastered."""
    by_id = {e.id: e for e in exercises}
    current = by_id.get(current_id)
    if current is None:
        raise KeyError(current_id)

    if not is_mastered(current, attempts):
        return {"current": current_id, "mastered": False,
                "next_exercise_id": current_id,
                "reason": _missing_reason(current, attempts)}

    mastered = {e.id for e in exercises if is_mastered(e, attempts)}
    ordered = sorted(exercises, key=lambda e: (e.difficulty, e.id))
    for ex in ordered:
        if ex.id in mastered:
            continue
        if all(p in mastered for p in ex.prerequisites):
            return {"current": current_id, "mastered": True,
                    "next_exercise_id": ex.id,
                    "reason": f"'{current_id}' dominado; próximo liberado: '{ex.id}'."}

    if len(mastered) == len(exercises):
        reason = "Todos os exercícios dominados."
    else:
        reason = f"'{current_id}' dominado; nenhum exercício liberado (pré-requisitos pendentes)."
    return {"current": current_id, "mastered": True, "next_exercise_id": None, "reason": reason}
