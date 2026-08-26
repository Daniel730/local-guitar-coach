"""Contract tests for EventTracker PENDING/COMMIT state machine (MVP-2).

These encode the state-machine contract derived from the crash investigation:
  - While in PENDING, self._open["last"] must track the latest frame observed
    in the active window (the OPEN note is not yet closed), so that on COMMIT
    _close(t) sees the real duration (last - start), not 0.
  - A divergent frame does NOT replace the pending candidate.
  - A candidate that never stabilizes is never promoted.
  - Notes below min_note_duration_s are discarded (noise/transient), NOT marked
    uncertain — uncertainty already means perceptual/confidence uncertainty.

Written BEFORE the patch, so they fail against the current (buggy) code.
"""
from perception.events import EventTracker
from perception.engine import MusicalEvent


def _e(ts, midi, note, conf=0.9, onset=False, freq=110.0):
    return MusicalEvent(
        timestamp=ts, frequency=freq, note=note, midi=midi,
        confidence=conf, amplitude=0.1, onset=onset,
    )


def _state(tr):
    """Snapshot of internal state for assertions."""
    o = tr._open
    if o is None:
        return {"start": None, "last": None, "pending": None, "pending_since": None}
    pend = o.get("pending")
    return {
        "start": o.get("start"),
        "last": o.get("last"),
        "pending": pend["midi"] if pend else None,
        "pending_since": pend["since"] if pend else None,
    }


def test_commit_retorna_nota_anterior():
    # A2 -> B2 -> B2 : commit must return NoteEvent(A2) with correct span.
    tr = EventTracker(stabilization_s=0.05)
    assert tr.process(_e(0.00, 45, "A2", onset=True)) is None
    assert tr.process(_e(0.04, 47, "B2")) is None
    r = tr.process(_e(0.10, 47, "B2"))
    # CRITICAL: the closed note spans A2.start (0.00) to the commit frame (0.10).
    assert r is not None, "commit must return the closed OPEN note"
    assert r.note == "A2"
    assert abs(r.start - 0.00) < 1e-9
    assert abs(r.end - 0.10) < 1e-9
    assert abs(r.duration - 0.10) < 1e-9
    # Sustain evidence for the promoted B2 (frame extra = note held, not a trick).
    tr.process(_e(0.14, 47, "B2"))
    fin = tr.finalize()
    assert fin[0].note == "B2"
    assert abs(fin[0].start - 0.04) < 1e-9
    assert abs(fin[0].end - 0.14) < 1e-9


def test_divergencia_nao_destroi_candidata():
    # A2 -> B2 -> C3 -> B2 : divergent C3 must not replace pending B2.
    tr = EventTracker(stabilization_s=0.05)
    tr.process(_e(0.00, 45, "A2", onset=True))
    tr.process(_e(0.04, 47, "B2"))
    r_div = tr.process(_e(0.07, 48, "C3"))
    assert r_div is None, "divergent frame must not commit"
    # pending must still be B2, not C3
    assert _state(tr)["pending"] == 47
    r = tr.process(_e(0.11, 47, "B2"))
    assert r is not None
    assert r.note == "A2"
    # Sustain evidence for the promoted B2 (frame extra = note held, not a trick).
    tr.process(_e(0.14, 47, "B2"))
    fin = tr.finalize()
    assert fin[0].note == "B2"


def test_candidata_nunca_estabiliza():
    # A2 -> B2 -> C3 -> D3 : candidate B2 never persists stabilization_s,
    # so NO commit of B2 should happen.
    tr = EventTracker(stabilization_s=0.05)
    tr.process(_e(0.00, 45, "A2", onset=True))
    tr.process(_e(0.04, 47, "B2"))   # pending B2 since 0.04
    tr.process(_e(0.07, 48, "C3"))   # divergent -> pending stays B2
    r = tr.process(_e(0.11, 50, "D3"))  # different again -> B2 never stabilized
    # No commit: the OPEN note A2 is still held (not closed+returned here).
    assert r is None, "candidate that never stabilizes must not be committed"
    # State must still be PENDING B2 (or held OPEN), NOT promoted to D3 as committed.
    assert _state(tr)["pending"] == 47


def test_mvp2_intacto():
    # E2 F#2 G2 A2 B2 must still produce the clean ascending sequence.
    # Reuse the engine path to honor the real MVP-2 property.
    import numpy as np
    from perception.engine import PerceptionEngine

    def _sine_blks(freq, sr=44100, dur=0.25, amp=0.4, blocksize=1024):
        total = int(sr * dur)
        t = np.arange(total) / sr
        wave = amp * np.sin(2 * np.pi * freq * t)
        return [wave[i:i + blocksize] for i in range(0, total, blocksize)]

    def _blocks(freq, gap=0.05):
        out = _sine_blks(freq)
        out.append(np.zeros(int(44100 * gap)))
        return out

    freqs = [82.41, 92.50, 98.00, 110.0, 123.47]
    eng = PerceptionEngine(sr=44100, analysis_window=4096)
    tracker = EventTracker()
    t = 0.0
    for f in freqs:
        for b in _blocks(f):
            ev = eng.process_block(b, timestamp=t)
            if ev is not None:
                tracker.process(ev)
            t += b.size / 44100
    out = list(tracker.events) + tracker.finalize()
    notes = [e.note for e in out]
    assert notes == ["E2", "F#2", "G2", "A2", "B2"], f"got {notes}"


def test_nota_abaixo_duracao_minima_descartada():
    # A2 -> B2 immediate: A2 lives 0.00->0.00 (no sustain), below min duration.
    # Per decision (a): discarded as noise/transient, NOT marked uncertain.
    tr = EventTracker()  # default min_note_duration_s = 0.04
    out = []
    r = tr.process(_e(0.00, 45, "A2", onset=True))
    assert r is None
    # Immediate switch to B2 (gap 0 < note_change_gap_s): A2 never sustained.
    r = tr.process(_e(0.00, 47, "B2"))
    # A2 was too short -> _close returns None (discarded), not a NoteEvent.
    assert r is None, "A2 below min duration must be discarded (None), not returned"
    # Finalize: only B2 should remain (A2 discarded).
    fin = tr.finalize()
    # B2 itself may also be too short here, but the contract is: A2 not present.
    assert all(e.note != "A2" for e in fin), "A2 must not appear as a NoteEvent"
