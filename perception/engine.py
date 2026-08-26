"""Perception Engine: combine pitch + onset + amplitude into MusicalEvents.

Consumes raw audio blocks via process_block(); maintains its own analysis
window and clock so it is deterministic and testable without a sound card.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

from .notes import freq_to_note
from .pitch import yin_estimate
from .onset import OnsetDetector


@dataclass
class MusicalEvent:
    timestamp: float
    frequency: float
    note: Optional[str]
    midi: Optional[int]
    confidence: float
    amplitude: float
    onset: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = round(self.timestamp, 3)
        d["frequency"] = round(self.frequency, 2)
        d["confidence"] = round(self.confidence, 2)
        d["amplitude"] = round(self.amplitude, 3)
        return d


class PerceptionEngine:
    def __init__(
        self,
        sr: int = 44100,
        analysis_window: int = 4096,
        fmin: float = 40.0,
        fmax: float = 2000.0,
        pitch_threshold: float = 0.5,
        amplitude_floor: float = 0.02,
        onset_threshold_db: float = -45.0,
        sustain_min_interval_s: float = 0.1,
    ) -> None:
        self.sr = sr
        self.window = analysis_window
        self.fmin = fmin
        self.fmax = fmax
        self.pitch_threshold = pitch_threshold
        self.amp_floor = amplitude_floor
        self.sustain_min_interval_s = sustain_min_interval_s
        self._buf = deque(maxlen=analysis_window)
        self._onset = OnsetDetector(threshold_db=onset_threshold_db)
        self._clock = 0.0
        self._last_emit = -1e9
        self._last_note: Optional[str] = None

    def reset(self) -> None:
        self._buf.clear()
        self._clock = 0.0
        self._last_emit = -1e9
        self._last_note = None
        self._onset._last_onset = -1e9
        self._onset._above = False

    def process_block(self, block, timestamp: Optional[float] = None) -> Optional[MusicalEvent]:
        """Feed one audio block. Returns a MusicalEvent or None."""
        x = np.asarray(block, dtype=np.float64).ravel()
        if x.size == 0:
            return None
        if timestamp is None:
            timestamp = self._clock
        self._clock = timestamp + x.size / self.sr

        self._buf.extend(x)
        if len(self._buf) < self.window:
            return None

        frame = np.array(self._buf)
        amplitude = float(np.sqrt(np.mean(frame * frame)))
        amp_db = 20.0 * np.log10(amplitude + 1e-9)

        freq, conf = yin_estimate(frame, self.sr, self.fmin, self.fmax)
        onset = self._onset.update(amp_db, timestamp)

        if freq is None or conf < self.pitch_threshold or amplitude < self.amp_floor:
            return None

        note, midi = freq_to_note(freq)

        # Throttle sustained-pitch updates: emit at most one per interval,
        # unless the note changed or an onset fired.
        if (
            not onset
            and note == self._last_note
            and (timestamp - self._last_emit) < self.sustain_min_interval_s
        ):
            return None

        event = MusicalEvent(
            timestamp=timestamp,
            frequency=freq,
            note=note,
            midi=midi,
            confidence=conf,
            amplitude=amplitude,
            onset=onset,
        )
        self._last_emit = timestamp
        self._last_note = note
        return event
