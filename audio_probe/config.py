"""Audio acquisition configuration (pure data + validation).

The Audio Engine owns acquisition settings only. It contains NO
pedagogical logic (ARCHITECTURE.md sec. 4.1).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BLOCK_SIZE = 1024
DEFAULT_CHANNELS = 1
DEFAULT_HOST_API = "MME"


@dataclass
class AudioConfig:
    device: Optional[int] = None
    channels: int = DEFAULT_CHANNELS
    sample_rate: int = DEFAULT_SAMPLE_RATE
    block_size: int = DEFAULT_BLOCK_SIZE
    host_api: Optional[str] = DEFAULT_HOST_API
    # requested_input_latency: 0.0 means PortAudio default.
    requested_input_latency: float = 0.0

    def validate(self) -> None:
        if self.channels not in (1, 2):
            raise ValueError(f"channels must be 1 or 2, got {self.channels}")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.block_size <= 0:
            raise ValueError("block_size must be positive")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AudioConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
