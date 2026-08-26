"""MVP-2 — Event Tracker tests (A: sustain, B: scale, C: bad attack).

Each test feeds raw pitch events (as the PerceptionEngine would emit them)
into the EventTracker and asserts the musical interpretation.
"""
import math
import numpy as np
import pytest

from perception.engine import MusicalEvent, PerceptionEngine
from perception.events import EventTracker, NoteEvent


def _raw(freq, t, onset=False, conf=1.0):
    note, midi = (None, None)
    if freq is not None:
        from perception.notes import freq_to_note
        note, midi = freq_to_note(freq)
    return MusicalEvent(
        timestamp=t, frequency=freq, note=note, midi=midi,
        confidence=conf, amplitude=0.1, onset=onset,
    )


def _track_from_blocks(blocks, sr=44100, **kw):
    """Run the real PerceptionEngine over synthetic blocks to get raw events,
    then feed them to a fresh EventTracker and return the full note sequence."""
    eng = PerceptionEngine(sr=sr, analysis_window=4096)
    tracker = EventTracker(**kw)
    t = 0.0
    for b in blocks:
        ev = eng.process_block(b, timestamp=t)
        if ev is not None:
            tracker.process(ev)
        t += b.size / sr
    out = list(tracker.events)  # notes already closed during the loop
    out += tracker.finalize()   # plus the one still open at the end
    return out


def _sine_blks(freq, sr=44100, dur=0.5, amp=0.4, blocksize=1024):
    """Synthesize a tone split into hardware-sized blocks (like the real stream)."""
    total = int(sr * dur)
    t = np.arange(total) / sr
    wave = amp * np.sin(2 * math.pi * freq * t)
    return [wave[i : i + blocksize] for i in range(0, total, blocksize)]


def _blocks(freq, sr=44100, dur=0.5, amp=0.4, gap=0.0, blocksize=1024):
    out = _sine_blks(freq, sr, dur, amp, blocksize)
    if gap > 0:
        out.append(np.zeros(int(sr * gap)))
    return out


# ---------- Teste A: sustentação ----------
def test_A_sustain_single_note():
    # E2 (82.41 Hz) sustained 0.6s
    blocks = _blocks(82.41, dur=0.6)
    events = _track_from_blocks(blocks)
    assert len(events) == 1, f"expected 1 NoteEvent, got {len(events)}"
    e = events[0]
    assert e.note == "E2"
    assert e.duration >= 0.4  # allow engine latency
    assert e.confidence > 0.8


# ---------- Teste B: escala simples ----------
def test_B_scale_order():
    # E F# G A B  (82.41, 92.50, 98.00, 110.0, 123.47)
    freqs = [82.41, 92.50, 98.00, 110.0, 123.47]
    blocks = []
    for f in freqs:
        blocks += _blocks(f, dur=0.25, gap=0.05)
    events = _track_from_blocks(blocks)
    notes = [e.note for e in events]
    assert notes == ["E2", "F#2", "G2", "A2", "B2"], f"got {notes}"


# ---------- Teste C: ataque problemático ----------
def test_C_bad_attack_collapses_to_one():
    # Raw detector on a hard pick can emit: 76 96 98 78 77 77 77
    # We feed those as raw events (simulating YIN output on the attack),
    # all onset on first frame.
    ts = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12]
    freqs = [76.0, 96.0, 98.0, 78.0, 77.0, 77.0, 77.0]
    tracker = EventTracker()
    out = []
    for t, f in zip(ts, freqs):
        ev = _raw(f, t, onset=(t == 0.0))
        closed = tracker.process(ev)
        if closed is not None:
            out.append(closed)
    for closed in tracker.finalize():
        out.append(closed)
    # Must collapse to a SINGLE D#2 event (midi 39), not four notes.
    assert len(out) == 1, f"expected 1 NoteEvent, got {len(out)}: {[e.note for e in out]}"
    e = out[0]
    assert e.note == "D#2", f"expected D#2, got {e.note}"
    assert e.midi == 39
    # The transient pitches should be recorded, not hidden.
    assert 96.0 in e.pitch_samples and 98.0 in e.pitch_samples


def test_C_bad_attack_raw_events_are_four_but_tracker_one():
    # Explicit contract check: raw layer is 7 samples; tracker yields 1.
    ts = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12]
    freqs = [76.0, 96.0, 98.0, 78.0, 77.0, 77.0, 77.0]
    raw = [_raw(f, t, onset=(t == 0.0)) for t, f in zip(ts, freqs)]
    assert len(raw) == 7  # raw layer unchanged
    tracker = EventTracker()
    closed = [c for c in (tracker.process(r) for r in raw) if c]
    closed += tracker.finalize()
    assert len(closed) == 1


# ---------- Confiança não escondida ----------
def test_uncertain_transition_flagged():
    # A weak sustained 'note' (low confidence) must be flagged, not dropped.
    ts = [0.0, 0.05, 0.10, 0.15]
    freqs = [110.0, 110.0, 110.0, 110.0]
    confs = [0.30, 0.35, 0.32, 0.34]  # all below uncertain_confidence (0.55)
    tracker = EventTracker()
    out = []
    for t, f, c in zip(ts, freqs, confs):
        ev = _raw(f, t, onset=(t == 0.0), conf=c)
        closed = tracker.process(ev)
        if closed is not None:
            out.append(closed)
    out += tracker.finalize()
    assert len(out) == 1
    assert out[0].uncertain is True
    assert out[0].confidence < 0.55
