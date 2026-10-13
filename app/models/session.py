"""Pydantic models for WebSocket messages and REST API."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ===== WebSocket messages (control) =====

class StartSession(BaseModel):
    type: str = "start_session"
    exercise_id: str
    channel: int = 1  # 0=CH1, 1=CH2
    sample_rate: int = 44100
    block_size: int = 1024


class StopSession(BaseModel):
    type: str = "stop_session"


class WSMessage(BaseModel):
    """Union of possible control messages from client."""
    type: str
    exercise_id: Optional[str] = None
    channel: Optional[int] = None
    sample_rate: Optional[int] = None
    block_size: Optional[int] = None


# ===== WebSocket messages (server -> client telemetry) =====

class PitchTelemetry(BaseModel):
    type: str = "pitch"
    note: Optional[str] = None
    cents: Optional[float] = None
    frequency: Optional[float] = None
    confidence: Optional[float] = None
    onset: bool = False


class MeterTelemetry(BaseModel):
    type: str = "meter"
    ch1: float
    ch2: float


class NoteEventTelemetry(BaseModel):
    type: str = "note_event"
    note: str
    midi: Optional[int] = None
    start: float
    end: float
    duration: float
    confidence: float
    attack_confidence: float
    uncertain: bool = False


class TeacherTelemetry(BaseModel):
    type: str = "teacher"
    action: str
    exercise_id: Optional[str] = None
    tempo: Optional[float] = None
    reason: Optional[str] = None
    spoken_feedback: Optional[str] = None
    source: str  # "llm" | "fallback" | "schema_fail" | "policy_fail"


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
    raw_events: List[Any] = field(default_factory=list)   # MusicalEvent objects
    last_teacher_decision: Optional[Any] = None
    blocks_processed: int = 0
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


class DeviceInfo(BaseModel):
    index: int
    name: str
    channels: int
    sample_rate: float


class SessionStartRequest(BaseModel):
    exercise_id: str
    channel: int = 1


class SessionStartResponse(BaseModel):
    session_id: str
    status: str = "started"


class SessionStopResponse(BaseModel):
    status: str = "stopped"