"""Live perception CLI (MVP-1 + MVP-2).

Runs the PerceptionEngine (YIN) against the M-Track Duo (or any input) and
prints raw MusicalEvents. With --track it also runs the MVP-2 EventTracker
and prints aggregated NoteEvents instead.

Also supports self-tests (no hardware) so the math is verifiable instantly.

Usage:
    python -m perception --self-test
    python -m perception --self-test --track
    python -m perception --device 1 --seconds 10
    python -m perception --device 1 --seconds 10 --track
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from audio_probe.config import AudioConfig
from audio_probe.devices import find_mtrack_duo, list_input_devices
from audio_probe.stream import AudioStream

from .engine import PerceptionEngine, MusicalEvent
from .events import EventTracker, NoteEvent
from .sequence import compare


def _synth_blocks(freq, sr, blocksize, n_blocks, amp=0.4):
    t0 = 0.0
    out = []
    for i in range(n_blocks):
        n = blocksize
        t = (t0 + np.arange(n) / sr)
        out.append(amp * np.sin(2 * math.pi * freq * t))
        t0 += n / sr
    return out


def _raw_scale_seq(sr=44100, bs=1024, note_dur=0.25, gap=0.05):
    """Synthesize E2 F#2 G2 A2 B2 with gaps, as hardware-sized blocks."""
    freqs = [82.41, 92.50, 98.00, 110.0, 123.47]
    seq = []
    for f in freqs:
        total = int(sr * note_dur)
        t = np.arange(total) / sr
        w = 0.4 * np.sin(2 * math.pi * f * t)
        seq += [w[i : i + bs] for i in range(0, total, bs)]
        seq.append(np.zeros(int(sr * gap)))
    return seq


def run_self_test(track: bool = False) -> int:
    sr = 44100
    bs = 1024
    eng = PerceptionEngine(sr=sr, analysis_window=4096)

    if track:
        # MVP-2: play a short scale and show aggregated NoteEvents.
        seq = _raw_scale_seq(sr, bs)
        tracker = EventTracker()
        t = 0.0
        print("SELF-TEST --track (synthetic E2 F#2 G2 A2 B2):")
        for b in seq:
            ev = eng.process_block(b, timestamp=t)
            if ev is not None:
                closed = tracker.process(ev)
                if closed is not None:
                    print("  " + json.dumps(closed.to_dict()))
            t += b.size / sr
        for ne in tracker.finalize():
            print("  " + json.dumps(ne.to_dict()))
        return 0

    # MVP-1 raw self-test.
    seq = (
        _synth_blocks(82.41, sr, bs, 18)
        + [np.zeros(bs) for _ in range(12)]
        + _synth_blocks(110.0, sr, bs, 18)
        + [np.zeros(bs) for _ in range(12)]
        + _synth_blocks(440.0, sr, bs, 18)
        + [np.random.default_rng(1).normal(0, 0.3, bs) for _ in range(12)]
    )
    t = 0.0
    print("SELF-TEST (synthetic E2 -> A2 -> A4 -> noise):")
    for b in seq:
        ev = eng.process_block(b, timestamp=t)
        if ev is not None:
            print("  " + json.dumps(ev.to_dict()))
        t += b.size / sr
    return 0


def run_live(device_index: int | None, seconds: float, debug: bool = False, track: bool = False, exercise: str = None) -> int:
    idx = device_index
    if idx is None:
        m = find_mtrack_duo()
        idx = m["index"] if m else None
        if idx is None:
            print("No M-Track Duo auto-detected. Use --device N.", file=sys.stderr)
            print("Available devices:", file=sys.stderr)
            for d in list_input_devices():
                print(f"  {d['index']}: {d['name']}", file=sys.stderr)
            return 2

    cfg = AudioConfig(device=idx, sample_rate=44100, block_size=1024, channels=1)
    eng = PerceptionEngine(sr=cfg.sample_rate, analysis_window=4096)
    tracker = EventTracker() if track else None

    raw_events: list = []
    note_events: list = []
    blocks = 0
    max_peak = 0.0

    def _on_meter(_reading):
        pass

    stream = AudioStream(cfg, idx, on_meter=_on_meter)
    base_cb = stream._callback

    def _cb(indata, frames, time_info, status):
        nonlocal blocks, max_peak
        block = indata[:, 0] if indata.shape[1] > 1 else indata.ravel()
        blocks += 1
        pk = float(np.max(np.abs(block)))
        max_peak = max(max_peak, pk)
        if debug:
            rms = float(np.sqrt(np.mean(block * block)))
            db = 20.0 * np.log10(rms + 1e-9)
            print(f"  block {blocks:4d} peak {pk:+.3f} rms {db:6.1f} dBFS", flush=True)
        ev = eng.process_block(block)
        if ev is not None:
            raw_events.append(ev)
            if tracker is None:
                print(json.dumps(ev.to_dict()), flush=True)
            else:
                closed = tracker.process(ev)
                if closed is not None:
                    note_events.append(closed)
                    print(json.dumps(closed.to_dict()), flush=True)
        base_cb(indata, frames, time_info, status)

    stream._callback = _cb
    stream.start()
    import time
    time.sleep(seconds)
    stream.stop()

    if tracker is not None:
        for ne in tracker.finalize():
            note_events.append(ne)
            print(json.dumps(ne.to_dict()), flush=True)

    if exercise is not None:
        # MVP-3: load exercise JSON and compare played NoteEvents.
        try:
            from exercises.exercise import load_exercise
            ex = load_exercise(exercise)
        except FileNotFoundError:
            print(f"EXERCISE NOT FOUND: {exercise}", file=sys.stderr)
            return 2
        except Exception as e:  # noqa
            print(f"EXERCISE ERROR: {e}", file=sys.stderr)
            return 2
        comp = compare(ex.id, ex.expected_sequence, note_events)
        print("\n=== COMPARISON (MVP-3 — what you should play vs what you played) ===")
        print(json.dumps(comp.to_dict(), indent=2))
        # No scoring printed (that is MVP-4).

    print(f"\nBlocks received: {blocks}")
    print(f"Max block peak : {max_peak:+.4f} ({20*np.log10(max_peak+1e-9):.1f} dBFS)")
    print(f"Raw pitch events : {len(raw_events)}")
    print(f"Note events      : {len(note_events)}")
    if blocks and not raw_events:
        print("DIAGNOSTIC: audio reached the callback but no pitch passed the engine.")
        print("  - If max peak is near 0.00: guitar not connected / gain at zero.")
        print("  - If peak is decent but no events: run --self-test to confirm engine math.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Local Guitar Coach — Perception (MVP-1+MVP-2)")
    p.add_argument("--device", type=int, default=None, help="input device index")
    p.add_argument("--seconds", type=float, default=10.0, help="live capture duration")
    p.add_argument("--self-test", action="store_true", help="synthesize known pitches, no hardware")
    p.add_argument("--debug", action="store_true", help="print per-block level (live mode)")
    p.add_argument("--track", action="store_true", help="run MVP-2 EventTracker (aggregated NoteEvents)")
    p.add_argument("--exercise", type=str, default=None, help="path to exercise JSON (MVP-3 comparison)")
    args = p.parse_args()

    if args.self_test:
        return run_self_test(track=args.track)
    return run_live(
        args.device, args.seconds,
        debug=args.debug, track=args.track, exercise=args.exercise,
    )


if __name__ == "__main__":
    raise SystemExit(main())
