"""MVP-0 probe orchestrator.

The single entry point that proves the first link of the chain:
  M-Track Duo -> Windows -> Python -> Audio captured successfully.

Per ARCH sec. 31, MVP-0 does NOT touch Ollama, voice, curriculum,
database, GUI, AI, songs or accounts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config import AudioConfig
from .devices import list_input_devices, resolve_device
from .meters import LevelMeter
from .stream import AudioStream

ProbeCallback = Callable[[Dict], None]


@dataclass
class ProbeResult:
    device_index: int
    device_name: str
    config: Dict
    duration_seconds: float
    max_peak: float
    latency: Dict[str, Optional[float]] = field(default_factory=dict)
    blocks_received: int = 0
    detected: bool = False  # True if any block exceeded the noise floor


class AudioProbe:
    def __init__(self, config: Optional[AudioConfig] = None, noise_floor: float = 0.01):
        self.config = config or AudioConfig()
        self.noise_floor = noise_floor

    def list_devices(self) -> List[Dict]:
        return list_input_devices()

    def run(self, seconds: float = 2.0, on_meter: Optional[ProbeCallback] = None) -> ProbeResult:
        device_index = resolve_device(
            config_device=self.config.device,
            host_api=self.config.host_api,
        )
        device_name = self._device_name(device_index)

        meter = LevelMeter()
        stream = AudioStream(self.config, device_index, meter=meter, on_meter=on_meter)

        blocks = 0

        def _count(*_a):
            nonlocal blocks
            blocks += 1

        if on_meter is None:
            stream._on_meter = _count
        else:
            orig = on_meter

            def _wrap(r):
                _count()
                orig(r)

            stream._on_meter = _wrap

        stream.start()
        try:
            time.sleep(seconds)
        finally:
            stream.stop()

        lat = stream.latency_stats()
        max_peak = stream.max_peak
        detected = max_peak >= self.noise_floor or blocks > 0

        return ProbeResult(
            device_index=device_index,
            device_name=device_name,
            config=self.config.to_dict(),
            duration_seconds=seconds,
            max_peak=max_peak,
            latency=lat,
            blocks_received=blocks,
            detected=detected,
        )

    def _device_name(self, index: int) -> str:
        for d in list_input_devices():
            if d["index"] == index:
                return d["name"]
        return f"device #{index}"


def quick_probe(seconds: float = 2.0) -> ProbeResult:
    return AudioProbe().run(seconds=seconds)
