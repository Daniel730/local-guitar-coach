"""MVP-3 — Sequence Matcher tests.

Covers the four required cases (insertion, deletion, substitution,
reordering) plus uncertain-not-auto-error, using string note lists and the
real compare() with NoteEvent objects.
"""
from perception.events import NoteEvent
from perception.sequence import (
    SequenceMatcher,
    compare,
    CORRECT,
    WRONG,
    MISSING,
    EXTRA,
    UNCERTAIN,
)


def _ev(note, uncertain=False, start=0.0, dur=0.15):
    return NoteEvent(
        note=note, midi=None, start=start, end=start + dur, duration=dur,
        confidence=0.9 if not uncertain else 0.3,
        attack_confidence=0.9, uncertain=uncertain, pitch_samples=[],
    )


def _statuses(comp):
    return [(a.expected, a.played, a.status) for a in comp.alignment]


# ---------- 1. Substitution (wrong note) ----------
def test_substitution_then_alignment():
    # Expected E G A B D, Played E G A A D  (A instead of B)
    exp = ["E2", "G2", "A2", "B2", "D3"]
    played = [_ev("E2"), _ev("G2"), _ev("A2"), _ev("A2"), _ev("D3")]
    comp = compare("x", exp, played)
    st = _statuses(comp)
    # B2 expected must map to A2 played = wrong; the rest correct
    assert ("B2", "A2", WRONG) in st
    assert ("E2", "E2", CORRECT) in st
    assert ("D3", "D3", CORRECT) in st
    assert ("G2", "G2", CORRECT) in st
    assert ("A2", "A2", CORRECT) in st


# ---------- 2. Reordering ----------
def test_reordering():
    # Expected E G A B, Played E A G B
    exp = ["E2", "G2", "A2", "B2"]
    played = [_ev("E2"), _ev("A2"), _ev("G2"), _ev("B2")]
    comp = compare("x", exp, played)
    st = _statuses(comp)
    # Alignment must NOT cascade-fail: E, G, B align correctly even though
    # A was played out of order. The misplaced A becomes extra + missing,
    # not a chain of wrong notes.
    assert ("E2", "E2", CORRECT) in st
    assert ("G2", "G2", CORRECT) in st
    assert ("B2", "B2", CORRECT) in st
    # The out-of-order A shows up as extra (played) and missing (expected).
    assert (None, "A2", EXTRA) in st
    assert ("A2", None, MISSING) in st
    # Critically: NO cascade of wrong on G/B/A.
    assert all(s != WRONG for (_, _, s) in st)


# ---------- 3. Deletion (missing) ----------
def test_deletion_missing():
    # Expected E G A B, Played E G B  (A missing)
    exp = ["E2", "G2", "A2", "B2"]
    played = [_ev("E2"), _ev("G2"), _ev("B2")]
    comp = compare("x", exp, played)
    st = _statuses(comp)
    assert ("A2", None, MISSING) in st
    assert ("E2", "E2", CORRECT) in st
    assert ("G2", "G2", CORRECT) in st
    assert ("B2", "B2", CORRECT) in st


# ---------- 4. Insertion (extra) ----------
def test_insertion_extra():
    # Expected E G A B D, Played E G F# A B D  (F# extra)
    exp = ["E2", "G2", "A2", "B2", "D3"]
    played = [_ev("E2"), _ev("G2"), _ev("F#2"), _ev("A2"), _ev("B2"), _ev("D3")]
    comp = compare("x", exp, played)
    st = _statuses(comp)
    # F#2 is extra, the rest still align correctly (no cascade failure)
    assert (None, "F#2", EXTRA) in st
    assert ("E2", "E2", CORRECT) in st
    assert ("G2", "G2", CORRECT) in st
    assert ("A2", "A2", CORRECT) in st
    assert ("B2", "B2", CORRECT) in st
    assert ("D3", "D3", CORRECT) in st


# ---------- 5. Uncertain NOT treated as error ----------
def test_uncertain_not_error():
    # A played note flagged uncertain must be 'uncertain', never 'wrong'/'correct'.
    exp = ["E2", "G2"]
    played = [_ev("E2"), _ev("G2", uncertain=True)]
    comp = compare("x", exp, played)
    st = _statuses(comp)
    assert ("E2", "E2", CORRECT) in st
    assert ("G2", "G2", UNCERTAIN) in st
    # No 'accuracy' key must exist anywhere.
    d = comp.to_dict()
    assert "accuracy" not in d
    assert "score" not in d


# ---------- 6. Timestamps preserved ----------
def test_timestamps_preserved():
    exp = ["E2", "G2"]
    played = [_ev("E2", start=1.0, dur=0.2), _ev("G2", start=1.4, dur=0.18)]
    comp = compare("x", exp, played)
    e2 = comp.alignment[0]
    g2 = comp.alignment[1]
    assert e2.played_start == 1.0 and e2.played_duration == 0.2
    assert g2.played_start == 1.4 and g2.played_duration == 0.18


# ---------- 7. Direct align semantics ----------
def test_align_basic():
    m = SequenceMatcher()
    al = m.align(["E2", "G2"], [("E2", False), ("G2", False)])
    assert al[0].status == CORRECT
    assert al[1].status == CORRECT
