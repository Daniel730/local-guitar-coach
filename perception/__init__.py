"""Perception Engine (MVP-1).

Deterministic musical analysis: YIN pitch -> frequency -> MIDI -> note,
plus a separate onset detector. No LLM is used to decide pitch or notes
(see ARCHITECTURE.md §5 / docs/MVP1_FUTURE_DESIGN.md).

This package consumes raw audio blocks (e.g. from audio_probe.AudioStream)
and emits MusicalEvents.
"""

from .notes import freq_to_midi, midi_to_note, freq_to_note, nearest_note_name
from .pitch import yin_estimate
from .onset import OnsetDetector
from .engine import MusicalEvent, PerceptionEngine

__all__ = [
    "freq_to_midi",
    "midi_to_note",
    "freq_to_note",
    "nearest_note_name",
    "yin_estimate",
    "OnsetDetector",
    "MusicalEvent",
    "PerceptionEngine",
]
