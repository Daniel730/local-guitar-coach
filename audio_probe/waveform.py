"""Circular waveform buffer for visualization.

Holds the most recent `capacity` samples; `snapshot()` returns them in
correct chronological order regardless of internal write position.
"""
from __future__ import annotations

import numpy as np


class WaveformBuffer:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._idx = 0
        self._filled = False

    def push(self, block: np.ndarray) -> None:
        block = np.asarray(block, dtype=np.float32).ravel()
        n = block.size
        if n == 0:
            return
        if n >= self.capacity:
            self._buf[:] = block[-self.capacity :]
            self._idx = 0
            self._filled = True
            return
        end = self._idx + n
        if end <= self.capacity:
            self._buf[self._idx : end] = block
        else:
            first = self.capacity - self._idx
            self._buf[self._idx :] = block[:first]
            self._buf[: end - self.capacity] = block[first:]
        self._idx = end % self.capacity
        self._filled = True

    def snapshot(self) -> np.ndarray:
        if not self._filled:
            return self._buf.copy()
        return np.concatenate((self._buf[self._idx :], self._buf[: self._idx]))
