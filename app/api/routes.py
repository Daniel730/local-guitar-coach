"""REST API routes."""
from __future__ import annotations
from typing import List
import json

from fastapi import APIRouter, HTTPException

from app.models.session import HealthResponse, ExerciseInfo, DeviceInfo
from exercises.curriculum import list_exercises as curriculum_exercises
from audio_probe.devices import list_input_devices
from pathlib import Path

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


def _info(ex) -> ExerciseInfo:
    return ExerciseInfo(
        id=ex.id,
        name=ex.name,
        target_notes=ex.target_notes,  # full melody for display; scoring uses expected_sequence
        difficulty=ex.difficulty,
        target_bpm=ex.target_bpm,
        start_bpm=ex.start_bpm,
        skill=ex.skill,
        description=ex.description,
    )


@router.get("/exercises", response_model=List[ExerciseInfo])
async def list_exercises() -> List[ExerciseInfo]:
    """All exercises in curriculum order (difficulty, id)."""
    return [_info(ex) for ex in curriculum_exercises()]


@router.get("/exercises/{exercise_id}", response_model=ExerciseInfo)
async def get_exercise(exercise_id: str) -> ExerciseInfo:
    ex = next((e for e in curriculum_exercises() if e.id == exercise_id), None)
    if ex is None:
        raise HTTPException(404, "Exercise not found")
    return _info(ex)


@router.get("/devices", response_model=List[DeviceInfo])
async def list_devices() -> List[DeviceInfo]:
    devices = []
    for d in list_input_devices():
        if d["max_input_channels"] > 0:
            devices.append(DeviceInfo(
                index=d["index"],
                name=d["name"],
                channels=d["max_input_channels"],
                sample_rate=d["default_sample_rate"],
            ))
    return devices


@router.get("/progress")
async def progress():
    """Per-skill progression + the 20 most recent performances from data/sessions/."""
    sessions_dir = Path("data") / "sessions"
    exercises = {ex.id: {"name": ex.name, "skill": ex.skill, "target_notes": ex.expected_sequence}
                 for ex in curriculum_exercises()}
    recent, skills = [], {}
    if sessions_dir.exists():
        files = sorted((f for f in sessions_dir.glob("*.json") if not f.name.startswith("skill_")),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        for path in files[:20]:
            try:
                recent.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        for path in sessions_dir.glob("skill_*.json"):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                skills[d["skill"]] = d
            except Exception:
                continue
    return {"exercises": exercises, "recent": recent, "skills": skills}


@router.get("/next")
async def next_step(current: str):
    """Deterministic progression (exercises.curriculum): repeat or advance."""
    from exercises import curriculum
    try:
        return curriculum.next_exercise(current, curriculum_exercises(), curriculum.load_attempts())
    except KeyError:
        raise HTTPException(404, "Exercise not found")
