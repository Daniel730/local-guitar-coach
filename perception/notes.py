"""Frequency <-> MIDI <-> note-name conversion.

Scientific pitch notation: MIDI 69 = A4 = 440 Hz; MIDI 60 = C4.
"""
from __future__ import annotations

import math

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def freq_to_midi(freq: float) -> float | None:
    """Convert a frequency in Hz to a (fractional) MIDI number.

    Returns None for non-positive input.
    """
    if freq is None or freq <= 0:
        return None
    return 69.0 + 12.0 * math.log2(freq / 440.0)


def midi_to_note(midi: float) -> str:
    """Convert a (rounded) MIDI number to scientific note name, e.g. 40 -> 'E2'."""
    m = int(round(midi))
    name = _NOTE_NAMES[m % 12]
    octave = m // 12 - 1
    return f"{name}{octave}"


def freq_to_note(freq: float) -> tuple[str | None, int | None]:
    """Return (note_name, rounded_midi) for a frequency, or (None, None)."""
    midi = freq_to_midi(freq)
    if midi is None:
        return None, None
    return midi_to_note(midi), int(round(midi))


def nearest_note_name(freq: float) -> str | None:
    """Nearest note name to a frequency (useful for stable display labels)."""
    midi = freq_to_midi(freq)
    if midi is None:
        return None
    return midi_to_note(midi)
