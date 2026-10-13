"""Fretboard Engine (CHANGE-08).

The single source of musical truth for the fretboard:
    - Standard tuning as an explicit, testable configuration.
    - FretPosition = (string 1..6, fret 0..N). Fret 0 == open string.
    - pitch_at(FretPosition) -> pitch name  (deterministic, no inference).
    - validate_target_note(...) -> list[str]  (rejects inconsistent pitch/position).

Tuning string numbering (high E string = 1, low E string = 6):

    string 1 = E4  (high E)
    string 2 = B3
    string 3 = G3
    string 4 = D3
    string 5 = A2
    string 6 = E2  (low E)

This is the canonical contract for the Fretboard Engine. Both the backend
(launcher of target-note data) and the frontend renderer consume it. There is
NO pitch -> position inference anywhere: a TargetNote always carries an explicit
position, and validate_target_note enforces that the pitch matches the position.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from perception.notes import note_to_freq, freq_to_midi, midi_to_note

# Standard guitar tuning, string -> open-string pitch name.
# String 1 = high E (highest), string 6 = low E (lowest).
STANDARD_TUNING: dict[int, str] = {
    6: "E2",
    5: "A2",
    4: "D3",
    3: "G3",
    2: "B3",
    1: "E4",
}

MIN_STRING = 1
MAX_STRING = 6
MIN_FRET = 0


@dataclass(frozen=True)
class FretPosition:
    """A position on the fretboard.

    string: 1 (high E) .. 6 (low E)
    fret:   0 = open string, 1..N = fretted
    """
    string: int
    fret: int

    def __post_init__(self) -> None:
        if not (MIN_STRING <= self.string <= MAX_STRING):
            raise ValueError(f"string must be in {MIN_STRING}..{MAX_STRING}, got {self.string}")
        if self.fret < MIN_FRET:
            raise ValueError(f"fret must be >= {MIN_FRET}, got {self.fret}")


# --- pitch <-> midi <-> position ---

def _tuning_midi() -> dict[int, int]:
    """Return the MIDI note number of each open string."""
    return {s: (freq_to_midi(note_to_freq(p)) if note_to_freq(p) else 0)
            for s, p in STANDARD_TUNING.items()}


def tuning_midi() -> dict[int, int]:
    """Public: MIDI note of each open string."""
    return dict(_tuning_midi())


def pitch_at(pos: FretPosition) -> str:
    """Compute the pitch name produced at a FretPosition on standard-tuned guitar.

    fret 0 -> open string. Each fret = +1 semitone.
    Deterministic: the single source of truth for position -> pitch.
    """
    if pos.string not in STANDARD_TUNING:
        raise ValueError(f"string {pos.string} not in tuning")
    base_midi = freq_to_midi(note_to_freq(STANDARD_TUNING[pos.string]))
    if base_midi is None:
        raise ValueError(f"could not resolve MIDI for open string {pos.string}")
    target_midi = round(base_midi) + pos.fret
    return midi_to_note(float(target_midi))


def is_open_string(pos: FretPosition) -> bool:
    return pos.fret == 0


def validate_target_note(note: dict) -> list[str]:
    """Validate a TargetNote dict against the musical contract.

    TargetNote shape:
        {
          "pitch":  "E2",          # scientific name, REQUIRED
          "position": {            # REQUIRED (never inferred from pitch)
            "string": 6,           # 1..6
            "fret":   0            # 0 = open
          },
        }

    Returns a list of human-readable problems (empty == valid).
    """
    problems: list[str] = []
    if not isinstance(note, dict):
        return ["target note must be an object"]

    pitch = note.get("pitch")
    if not pitch or not isinstance(pitch, str):
        problems.append("pitch is required and must be a string")

    position = note.get("position")
    if position is None or not isinstance(position, dict):
        problems.append("position is required (no pitch->position inference)")

    if "string" in (position or {}) and "fret" in (position or {}):
        try:
            string = int(position["string"])
            fret = int(position["fret"])
        except (TypeError, ValueError):
            problems.append("position.string and position.fret must be integers")
            return problems
        if not (MIN_STRING <= string <= MAX_STRING):
            problems.append(f"position.string out of range {MIN_STRING}..{MAX_STRING}")
        if fret < MIN_FRET:
            problems.append(f"position.fret must be >= {MIN_FRET}")
        # pitch <-> position consistency (the core guarantee)
        if pitch and "string" not in problems and fret >= MIN_FRET:
            try:
                computed = pitch_at(FretPosition(string=string, fret=fret))
                if computed != pitch:
                    problems.append(
                        f"pitch '{pitch}' inconsistent with position "
                        f"string={string}, fret={fret} (expected '{computed}')"
                    )
            except ValueError as e:
                problems.append(f"position invalid: {e}")
    return problems


def validate_exercise_notes(notes: list[dict]) -> list[str]:
    """Validate every TargetNote in an exercise's target_notes list."""
    problems: list[str] = []
    for i, note in enumerate(notes):
        for p in validate_target_note(note):
            problems.append(f"target_notes[{i}]: {p}")
    return problems
