"""MVP-2 EventTracker regression tests.

The critical one reproduces the exact crash seen in live validation:
a note opens, a pending candidate is created during stabilization, and the
candidate persists long enough to commit a switch — which previously called
_close() (setting self._open = None) and THEN read self._open["pending"]["since"],
raising 'NoneType' object is not subscriptable'.

We assert it now produces a clean sequence with no exception and correct
start times (the new note starts at the pending candidate's 'since').
"""
from perception.events import EventTracker
from perception.engine import MusicalEvent


def _e(ts, midi, note, conf=0.9, onset=False, freq=110.0):
    # MusicalEvent is a dataclass: (timestamp, frequency, note, midi, confidence, amplitude, onset)
    return MusicalEvent(
        timestamp=ts, frequency=freq, note=note, midi=midi,
        confidence=conf, amplitude=0.1, onset=onset,
    )


def test_commit_switch_no_crash():
    # A2 open, then brief B2 (pending), then B2 persists -> commit switch.
    # Gaps must be < note_change_gap_s (0.12) so we stay in stabilization.
    tr = EventTracker(stabilization_s=0.05)
    out = []
    # A2 onset
    r = tr.process(_e(0.00, 45, "A2", onset=True))
    assert r is None
    # B2 appears (pending candidate) at 0.04
    r = tr.process(_e(0.04, 47, "B2"))
    assert r is None
    # B2 persists -> commit switch at 0.10 (>= stabilization 0.05, gap 0.06<0.12)
    r = tr.process(_e(0.10, 47, "B2"))
    # Must close A2 and return it, then open B2 starting at 0.04.
    assert r is not None
    assert r.note == "A2"
    # The returned closed event must span from A2.start (0.00) to switch (0.10).
    assert abs(r.start - 0.00) < 1e-9
    assert abs(r.end - 0.10) < 1e-9
    # Now B2 is OPEN.
    r2 = tr.process(_e(0.14, 47, "B2"))
    assert r2 is None
    # finalize closes B2
    fin = tr.finalize()
    assert len(fin) == 1
    assert fin[0].note == "B2"
    assert abs(fin[0].start - 0.04) < 1e-9  # starts at pending 'since'


def test_divergent_frame_during_pending_no_crash():
    # A2 open, pending B2 created, then a stray C3 frame arrives before B2
    # persists -> must NOT swap candidate, must NOT crash.
    tr = EventTracker(stabilization_s=0.05)
    tr.process(_e(0.00, 45, "A2", onset=True))  # OPEN A2
    tr.process(_e(0.04, 47, "B2"))               # PENDING B2
    # divergent C3 frame (midi 48) — should be ignored for candidate purposes
    r = tr.process(_e(0.07, 48, "C3"))
    assert r is None
    # B2 returns and persists -> commit switch to B2 (not C3)
    r = tr.process(_e(0.11, 47, "B2"))
    assert r is not None
    assert r.note == "A2"
    # Extra B2 frame provides sustained evidence so the promoted B2
    # satisfies min_note_duration_s before finalize().
    tr.process(_e(0.14, 47, "B2"))
    fin = tr.finalize()
    assert fin[0].note == "B2"


def test_no_exception_on_many_transitions():
    # Stress: a long alternating sequence must never raise.
    tr = EventTracker(stabilization_s=0.04)
    notes = [(45, "A2"), (47, "B2"), (48, "C3"), (50, "D3"), (45, "A2")]
    ts = 0.0
    for _ in range(50):
        for midi, note in notes:
            ts += 0.05
            tr.process(_e(ts, midi, note, onset=(ts % 0.25 == 0)))
    # should not raise; finalize cleanly
    fin = tr.finalize()
    assert isinstance(fin, list)


def test_invariants_held():
    # After processing, internal state must always be IDLE or OPEN (pending may
    # be set, but _open is never None mid-OPEN with pending access crashing).
    tr = EventTracker(stabilization_s=0.04)
    for i in range(100):
        midi = 40 + (i % 5)
        tr.process(_e(i * 0.05, midi, "X"))
    # _open is either None (IDLE) or a dict (OPEN/PENDING) — never partially
    # destroyed. If it is a dict, pending key exists.
    if tr._open is not None:
        assert "pending" in tr._open
