"""MVP-3 — Exercise Loader + end-to-end comparison with real NoteEvents.

Loads a JSON exercise (no DB) and compares against played NoteEvents via the
SequenceMatcher. Confirms the four required pieces are wired together.
"""
import json
from pathlib import Path

from exercises.exercise import load_exercise, exercise_from_dict
from perception.events import NoteEvent
from perception.sequence import compare, WRONG, CORRECT, MISSING, EXTRA, UNCERTAIN


def _ev(note, uncertain=False, start=0.0, dur=0.15):
    return NoteEvent(
        note=note, midi=None, start=start, end=start + dur, duration=dur,
        confidence=0.9 if not uncertain else 0.3,
        attack_confidence=0.9, uncertain=uncertain, pitch_samples=[],
    )


def test_load_exercise_from_dict():
    data = {
        "id": "scale_e_minor_001",
        "name": "E Minor Pentatonic",
        "skill": "pentatonic",
        "difficulty": 1,
        "target_notes": ["E2", "G2", "A2", "B2", "D3", "E3"],
    }
    ex = exercise_from_dict(data)
    assert ex.id == "scale_e_minor_001"
    assert ex.expected_sequence == ["E2", "G2", "A2", "B2", "D3", "E3"]
    assert ex.skill == "pentatonic"


def test_load_exercise_file(tmp_path):
    p = tmp_path / "ex.json"
    p.write_text(json.dumps({
        "id": "x1", "name": "X", "skill": "s", "difficulty": 2,
        "target_notes": ["E2", "G2"],
    }), encoding="utf-8")
    ex = load_exercise(p)
    assert ex.id == "x1"
    assert ex.expected_sequence == ["E2", "G2"]


def test_exercise_missing_required_raises():
    import pytest
    with pytest.raises(ValueError):
        exercise_from_dict({"id": "x"})  # no target_notes


def test_real_exercise_comparison():
    # Load the shipped example and play a slightly-off attempt:
    # Expected: E2 G2 A2 B2 D3 E3
    # Played:   E2 G2 A2 A2 D3 E3  (B2 -> wrong A2)
    ex = exercise_from_dict({
        "id": "scale_e_minor_001", "name": "E Minor Pentatonic",
        "skill": "pentatonic", "difficulty": 1,
        "target_notes": ["E2", "G2", "A2", "B2", "D3", "E3"],
    })
    played = [
        _ev("E2", start=0.0, dur=0.2),
        _ev("G2", start=0.3, dur=0.2),
        _ev("A2", start=0.6, dur=0.2),
        _ev("A2", start=0.9, dur=0.2),   # wrong, should be B2
        _ev("D3", start=1.2, dur=0.2),
        _ev("E3", start=1.5, dur=0.2),
    ]
    comp = compare(ex.id, ex.expected_sequence, played)
    d = comp.to_dict()
    # No scoring keys (MVP-4 territory).
    assert "accuracy" not in d
    assert "score" not in d
    assert "note_accuracy" not in d
    # B2 expected maps to A2 played = wrong; others correct.
    assert ("B2", "A2", WRONG) in [(a.expected, a.played, a.status) for a in comp.alignment]
    # Timestamps preserved on a correct note.
    e2 = [a for a in comp.alignment if a.expected == "E2" and a.played == "E2"][0]
    assert e2.played_start == 0.0 and e2.played_duration == 0.2
