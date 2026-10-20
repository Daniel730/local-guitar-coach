"""REST API routes."""
from __future__ import annotations
from typing import List
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.session import (
    HealthResponse, ExerciseInfo, DeviceInfo,
    SessionStartRequest, SessionStartResponse, SessionStopResponse,
)
from exercises.exercise import load_exercise
from audio_probe.devices import list_input_devices
from pathlib import Path

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/exercises", response_model=List[ExerciseInfo])
async def list_exercises() -> List[ExerciseInfo]:
    """All exercises in curriculum order (difficulty, id)."""
    from exercises.curriculum import list_exercises as curriculum_exercises
    return [
        ExerciseInfo(
            id=ex.id,
            name=ex.name,
            target_notes=ex.expected_sequence,
            difficulty=ex.difficulty,
            target_bpm=ex.target_bpm,
            start_bpm=ex.start_bpm,
            skill=ex.skill,
            description=ex.description,
        )
        for ex in curriculum_exercises()
    ]


@router.get("/exercises/{exercise_id}", response_model=ExerciseInfo)
async def get_exercise(exercise_id: str) -> ExerciseInfo:
    import os
    path = os.path.join("exercises", f"{exercise_id}.json")
    try:
        ex = load_exercise(path)
        return ExerciseInfo(
            id=ex.id,
            name=ex.name,
            target_notes=ex.expected_sequence,
            difficulty=ex.difficulty,
            target_bpm=ex.target_bpm,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Exercise not found")


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
    """Aggregate per-skill progression + recent sessions from data/sessions/."""
    sessions_dir = Path("data") / "sessions"
    exercises = {}
    import os as _os
    if _os.path.isdir("exercises"):
        for fname in _os.listdir("exercises"):
            if fname.endswith(".json"):
                ex_id = fname[:-5]
                try:
                    ex = load_exercise(find_exercise_path(ex_id))
                    exercises[ex_id] = {"name": ex.name, "skill": ex.skill, "target_notes": ex.expected_sequence}
                except Exception:
                    continue

    # Recent performance results (performed sessions)
    recent = []
    if sessions_dir.exists():
        for path in sorted(sessions_dir.glob("*.json")):
            if path.name.startswith("skill_"):
                continue
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                recent.append(d)
            except Exception:
                continue
        recent = sorted(recent, key=lambda r: r.get("performed_bpm") is not None, reverse=True)[:20]

    # Skill states
    skills = {}
    if sessions_dir.exists():
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
    exercises = curriculum.list_exercises()
    try:
        return curriculum.next_exercise(current, exercises, curriculum.load_attempts())
    except KeyError:
        raise HTTPException(404, "Exercise not found")


def find_exercise_path(ex_id: str) -> str:
    p = Path("exercises") / f"{ex_id}.json"
    return str(p) if p.exists() else f"exercises/{ex_id}.json"


# Serve frontend
@router.get("/api/")
async def api_root():
    return {"status": "ok", "version": "0.6.0"}