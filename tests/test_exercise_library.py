"""Every exercise/song in exercises/ must load, validate and be playable."""
import pytest

from exercises.curriculum import list_exercises
from exercises.exercise import exercise_from_dict, validate_exercise
from perception.fretboard import tuning_midi
from perception.notes import note_to_midi

EXERCISES = list_exercises()
IDS = {e.id for e in EXERCISES}


def test_library_size():
    assert len(EXERCISES) >= 12
    assert any(e.skill == "songs" for e in EXERCISES)


@pytest.mark.parametrize("ex", EXERCISES, ids=lambda e: e.id)
def test_exercise_valid_and_playable(ex):
    assert validate_exercise(ex) == []
    assert all(p in IDS and p != ex.id for p in ex.prerequisites)
    opens = tuning_midi().values()
    for n in ex.target_notes:
        midi = note_to_midi(n)
        assert midi is not None, n
        assert any(0 <= midi - o <= 12 for o in opens), f"{n} not playable in frets 0-12"


def test_collapse_repeats_only_for_songs():
    base = {"id": "x", "name": "x", "skill": "songs", "subskill": "melody", "difficulty": 1,
            "target_notes": ["E3", "E3", "F3", "E3"], "start_bpm": 60, "target_bpm": 90,
            "subdivision": "quarter"}
    assert exercise_from_dict(base).expected_sequence == ["E3", "E3", "F3", "E3"]
    song = exercise_from_dict({**base, "rules": {"collapse_repeats": True}})
    assert song.expected_sequence == ["E3", "F3", "E3"]
