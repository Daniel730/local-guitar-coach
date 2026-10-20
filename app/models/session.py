"""Pydantic models for WebSocket messages and REST API."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ===== WebSocket messages (server -> client telemetry) =====

class PitchTelemetry(BaseModel):
    type: str = "pitch"
    note: Optional[str] = None
    cents: Optional[float] = None
    frequency: Optional[float] = None
    confidence: Optional[float] = None
    onset: bool = False


class SessionStateTelemetry(BaseModel):
    type: str = "session_state"
    status: str  # "running" | "stopped" | "error"
    exercise: Optional[str] = None
    target_bpm: Optional[float] = None


class ErrorTelemetry(BaseModel):
    type: str = "error"
    message: str


# ===== Session state (in-memory) =====

@dataclass
class Session:
    exercise_id: str
    channel: int
    sample_rate: int
    block_size: int
    target_bpm: float
    subdivision: str
    start_bpm: float
    status: str = "running"  # running | stopped | error
    note_events: List[Any] = field(default_factory=list)  # NoteEvent objects
    session_id: str = ""


# ===== REST models =====

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.6.0"


class ExerciseInfo(BaseModel):
    id: str
    name: str
    target_notes: List[str]
    difficulty: int
    target_bpm: Optional[float] = None
    start_bpm: Optional[float] = None
    skill: Optional[str] = None
    description: Optional[str] = None


class DeviceInfo(BaseModel):
    index: int
    name: str
    channels: int
    sample_rate: float


    status: str = "stopped"