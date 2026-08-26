"""Level metering primitives.

All functions are pure (operate on a numpy block) so they are trivially
unit-testable with synthetic audio.
"""
from __future__ import annotations

import math

import numpy as np


def rms(block: np.ndarray) -> float:
    block = np.asarray(block, dtype=np.float64).ravel()
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block))))


def peak(block: np.ndarray) -> float:
    block = np.asarray(block, dtype=np.float64).ravel()
    if block.size == 0:
        return 0.0
    return float(np.max(np.abs(block)))


def to_dbfs(value: float) -> float:
    if value <= 0.0:
        return float("-inf")
    return float(20.0 * math.log10(value))


def dbfs_rms(block: np.ndarray) -> float:
    return to_dbfs(rms(block))


def dbfs_peak(block: np.ndarray) -> float:
    return to_dbfs(peak(block))


class LevelMeter:
    """Rolling meter that smooths RMS and holds peak decay."""

    def __init__(self, smoothing: float = 0.3, peak_hold_decay: float = 0.95):
        if not 0.0 <= smoothing <= 1.0:
            raise ValueError("smoothing must be in [0, 1]")
        self._alpha = smoothing
        self._peak_decay = peak_hold_decay
        self._peak_hold = 0.0
        self._rms_smoothed = 0.0

    def update(self, block: np.ndarray) -> dict:
        r = rms(block)
        p = peak(block)
        self._peak_hold = max(self._peak_hold * self._peak_decay, p)
        self._rms_smoothed = self._alpha * r + (1 - self._alpha) * self._rms_smoothed
        return {
            "rms": r,
            "peak": p,
            "rms_smoothed": self._rms_smoothed,
            "rms_dbfs": to_dbfs(r),
            "peak_dbfs": to_dbfs(p),
            "peak_hold": self._peak_hold,
            "peak_hold_dbfs": to_dbfs(self._peak_hold),
        }

    @property
    def peak_hold(self) -> float:
        return self._peak_hold
