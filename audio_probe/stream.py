"""Audio capture stream.

Owns the PortAudio input stream. Routes incoming blocks to the level
meter and waveform buffer and collects latency statistics. It performs
NO pitch/event analysis (that is the Perception Engine, MVP-1+).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import numpy as np
import sounddevice as sd

from .config import AudioConfig
from .meters import LevelMeter
from .waveform import WaveformBuffer

MeterCallback = Callable[[Dict], None]


class AudioStream:
    def __init__(
        self,
        config: AudioConfig,
        device_index: int,
        waveform_capacity: int = 2048,
        meter: Optional[LevelMeter] = None,
        on_meter: Optional[MeterCallback] = None,
    ):
        config.validate()
        self.config = config
        self.device_index = device_index
        self.waveform = WaveformBuffer(waveform_capacity)
        self.meter = meter or LevelMeter()
        self._on_meter = on_meter
        self._latencies: List[float] = []
        self._max_peak = 0.0
        self._stream: Optional[sd.InputStream] = None
        self._configured_latency: Optional[float] = None
        self._running = False

        def _callback(indata, frames, time_info, status):
            if status:
                pass  # status is an enum, not raised; ignore in MVP-0
            block = indata[:, 0] if indata.shape[1] > 1 else indata.ravel()
            self.waveform.push(block)
            reading = self.meter.update(block)
            self._max_peak = max(self._max_peak, reading["peak"])
            try:
                in_lat = float(time_info.inputBufferAdcTime)
            except (AttributeError, TypeError):
                in_lat = None
            # MME reports inputBufferAdcTime as 0; only keep nonzero samples.
            if in_lat and in_lat == in_lat and in_lat > 0:
                self._latencies.append(in_lat)
            if self._on_meter:
                self._on_meter(reading)

        self._callback = _callback

    def start(self) -> None:
        if self._running:
            return
        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.config.channels,
            samplerate=self.config.sample_rate,
            blocksize=self.config.block_size,
            latency=self.config.requested_input_latency or "low",
            callback=self._callback,
        )
        self._stream.start()
        try:
            self._configured_latency = float(self._stream.latency)
        except (AttributeError, TypeError):
            self._configured_latency = None
        self._running = True

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        self._stream = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def captured_waveform(self) -> np.ndarray:
        return self.waveform.snapshot()

    def latency_stats(self) -> Dict[str, Optional[float]]:
        if self._latencies:
            arr = np.array(self._latencies)
            return {
                "mean": float(np.mean(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "samples": int(arr.size),
                "source": "callback",
            }
        # MME (and some backends) report 0 in time_info; fall back to the
        # stream's configured input latency, which PortAudio resolves.
        if self._configured_latency is not None:
            return {
                "mean": self._configured_latency,
                "min": self._configured_latency,
                "max": self._configured_latency,
                "samples": 0,
                "source": "configured",
            }
        return {"mean": None, "min": None, "max": None, "samples": 0, "source": "none"}

    @property
    def max_peak(self) -> float:
        return self._max_peak
