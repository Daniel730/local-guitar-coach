"""AudioService — captures audio DIRECTLY from the M-Track (sounddevice).

Reverted to the project's original architecture (per Dan 2026-09): audio capture
lives in Python via audio_probe.AudioStream, exactly as coach.py does. The browser
is NOT an audio source — it only plots telemetry.

Channels/levels are measured on the real hardware (same as coach.py --channel),
and the chosen channel feeds the existing PerceptionEngine + EventTracker.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional, List
import numpy as np

from audio_probe.config import AudioConfig as _PortAudioConfig
from audio_probe.stream import AudioStream as _PortAudioStream
from perception.engine import PerceptionEngine
from perception.events import EventTracker, NoteEvent

logger = logging.getLogger(__name__)

# Log every Nth block's meter to avoid spamming (1024 blocks ≈ 23ms each).
METER_LOG_EVERY = 200  # ~4.6s at 44100/1024


@dataclass
class AudioConfig:
    device: int = 1          # M-Track device index
    sample_rate: int = 44100
    block_size: int = 1024
    channel: int = 1         # 0=CH1, 1=CH2 (explicit; not assumed)
    channels: int = 2        # open stereo, select in callback
    gain: float = 4.0        # digital gain (×) applied before perception
    amplitude_floor: float = 0.01   # perception amp floor (-40dBFS); below-noise rejection


class AudioService:
    """Captures from the physical device and runs the perception pipeline.

    Pure-Python, no browser involved. Telemetry is emitted via callbacks.
    """

    def __init__(
        self,
        config: AudioConfig,
        on_pitch: Optional[Callable[[object], None]] = None,
        on_note_event: Optional[Callable[[NoteEvent], None]] = None,
        on_meter: Optional[Callable[[List[float]], None]] = None,
    ) -> None:
        self.config = config
        self.on_pitch = on_pitch
        self.on_note_event = on_note_event
        self.on_meter = on_meter

        self._engine = PerceptionEngine(sr=config.sample_rate, analysis_window=4096,
                                        amplitude_floor=config.amplitude_floor)
        self._tracker = EventTracker()
        self._stream: Optional[_PortAudioStream] = None
        self._running = False
        self.blocks_processed = 0
        self._max_peak = 0.0

    # --- lifecycle ---
    def start(self) -> None:
        if self._running:
            return
        logger.info("[audio] start device=%s ch=%s chs=%s sr=%s gain=%s floor=%s",
                    self.config.device, self.config.channel, self.config.channels,
                    self.config.sample_rate, self.config.gain, self.config.amplitude_floor)
        self._engine.reset()
        self._tracker.reset()
        self.blocks_processed = 0
        self._max_peak = 0.0

        cfg = _PortAudioConfig(
            device=self.config.device,
            sample_rate=self.config.sample_rate,
            block_size=self.config.block_size,
            channels=self.config.channels,   # open stereo
        )
        stream = _PortAudioStream(cfg, self.config.device, on_meter=lambda _: None)
        base_cb = stream._callback
        self._chosen = self.config.channel

        def _cb(indata, frames, time_info, status):
            nonlocal base_cb
            block = indata[:, self._chosen] if indata.shape[1] > self._chosen else indata.ravel()
            self.blocks_processed += 1
            pk = float(np.max(np.abs(block)))
            self._max_peak = max(self._max_peak, pk)
            # meter: report RAW peak (hardware truth) + gated RMS for display
            if self.on_meter:
                amp = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
                self.on_meter([20 * np.log10(amp + 1e-9), 20 * np.log10(pk + 1e-9)])
                # throttled meter log so we don't flood the console
                if self.blocks_processed % METER_LOG_EVERY == 0:
                    logger.info("[audio] block=%s peak=%.1f dBFS",
                                self.blocks_processed, 20 * np.log10(pk + 1e-9))
            # digital gain applied to the block before perception
            g = self.config.gain
            block64 = block.astype(np.float64) * g
            ev = self._engine.process_block(block64)
            if ev is not None:
                logger.info("[audio] pitch note=%s freq=%.2f conf=%.2f onset=%s",
                            ev.note, ev.frequency, ev.confidence, ev.onset)
                if self.on_pitch:
                    self.on_pitch(ev)
                closed = self._tracker.process(ev)
                if closed is not None:
                    logger.info("[audio] note_event %s midi=%s dur=%.3f conf=%.2f",
                                closed.note, closed.midi, closed.duration, closed.confidence)
                    if self.on_note_event:
                        self.on_note_event(closed)
            base_cb(indata, frames, time_info, status)

        stream._callback = _cb
        self._stream = stream
        try:
            stream.start()
            self._running = True
            logger.info("[audio] started OK (chosen channel %s)", self._chosen)
        except Exception as e:
            logger.exception("[audio] FAILED to start capture: %s", e)
            raise

    def stop(self) -> None:
        logger.info("[audio] stop (blocks=%s)", self.blocks_processed)
        if self._stream is not None:
            self._stream.stop()
            self._stream = None
        # finalize any open note
        if self.on_note_event:
            for ne in self._tracker.finalize():
                logger.info("[audio] finalized note %s", ne.note)
                self.on_note_event(ne)
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def measure_channels(self, seconds: float = 1.0) -> List[float]:
        """Measure per-channel peak dBFS before capture (like coach.py)."""
        cfg = _PortAudioConfig(device=self.config.device, sample_rate=self.config.sample_rate,
                               block_size=self.config.block_size, channels=2)
        peaks = None

        def _cb(indata, frames, ti, status):
            nonlocal peaks
            if peaks is None:
                peaks = np.zeros(indata.shape[1])
            for ch in range(indata.shape[1]):
                peaks[ch] = max(peaks[ch], float(np.max(np.abs(indata[:, ch]))))

        stream = _PortAudioStream(cfg, self.config.device, on_meter=lambda _: None)
        stream._callback = _cb
        logger.info("[audio] measure_channels device=%s for %.1fs", self.config.device, seconds)
        stream.start()
        try:
            time.sleep(seconds)
        finally:
            stream.stop()
        if peaks is None:
            logger.info("[audio] measure_channels: no data")
            return []
        result = [round(20 * np.log10(float(p) + 1e-9), 1) for p in peaks]
        logger.info("[audio] measure_channels: CH1=%.1f CH2=%.1f dBFS", result[0], result[1] if len(result) > 1 else float("nan"))
        return result

    def get_note_events(self) -> List[NoteEvent]:
        return list(self._tracker.events)

    def reset_tracker(self) -> None:
        self._tracker.reset()