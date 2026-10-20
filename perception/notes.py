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


def note_to_midi(note_name: str) -> int | None:
    """Convert a scientific note name (e.g. 'E2', 'F#3') to a MIDI number.

    A4 = 69 = 440 Hz. Equal temperament. Returns None for unparseable names.
    """
    import re
    m = re.fullmatch(r"([A-G])(?:#|b)?(-?\d+)", note_name or "")
    if not m:
        return None
    letter, oct_str = m.group(1), m.group(2)
    # Octave string may still include an accidental adjacency if the regex
    # split; re-derive the accidental by checking the full name directly.
    accidental = ""
    if len(note_name) > 1 and note_name[1] in ("#", "b"):
        accidental = note_name[1]
    name = letter + accidental
    if name not in _NOTE_NAMES:
        return None
    semis = _NOTE_NAMES.index(name)
    octave = int(oct_str)
    return (octave + 1) * 12 + semis


def note_to_freq(note_name: str) -> float | None:
    """Convert a scientific note name (e.g. 'E2') to a frequency in Hz.

    Assumes A4 = 440 Hz, equal temperament. Inverse of freq_to_note.
    Returns None for unparseable names.
    """
    midi = note_to_midi(note_name)
    if midi is None:
        return None
    return 440.0 * pow(2.0, (midi - 69) / 12.0)
