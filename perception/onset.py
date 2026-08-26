"""Onset detection (separate component from pitch, per MVP-1 design).

Energy-based: fires when the RMS level (in dBFS) crosses up through a
threshold after a refractory period of relative silence. Kept independent
from pitch so each can be tested and tuned alone.
"""
from __future__ import annotations


class OnsetDetector:
    def __init__(
        self,
        threshold_db: float = -45.0,
        refractory_s: float = 0.08,
    ) -> None:
        self.threshold_db = threshold_db
        self.refractory_s = refractory_s
        self._last_onset = -1e9
        self._above = False

    def update(self, rms_db: float, t: float) -> bool:
        """Feed the current RMS (dBFS) and timestamp (s). Returns True on onset."""
        above = rms_db > self.threshold_db
        onset = False
        if above and not self._above:
            if t - self._last_onset >= self.refractory_s:
                onset = True
                self._last_onset = t
        self._above = above
        return onset
