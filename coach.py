"""Full-stack validation entrypoint (MVP-0 -> MVP-5).

Runs the ENTIRE pedagogical chain against the M-Track Duo in one live session:

    Guitar -> AudioStream -> YIN -> EventTracker -> SequenceMatcher
           -> PerformanceEvaluator -> TeacherContext -> Ollama -> Schema
           -> Policy -> Teacher Action

It deliberately supports an ADVERSARIAL mode (kill Ollama, play wrong, play
off-time, play under tempo) and WRITES structured artifacts to
validation/<session>/ for later human analysis.

AUDIO CHANNEL POLICY (per project decision 2026-08-26):
    The coach NEVER hardcodes indata[:,0]. The input channel is explicit
    (--channel 0/1) or auto-detected (--auto-channel) WITH user notification.
    Auto-detection is NOT silent: the per-channel dBFS report is printed and
    saved so the user knows which channel carries the guitar. Channel 2 is not
    assumed correct — it is whatever the report shows.

This is a validation harness, not the production app shell — it logs
everything and never hides a failure.

Usage:
    python -m coach --device 1 --seconds 12 --exercise exercises/scale_e_minor_001.json \
        --session validation/session_001 --student beginner --channel 1
    python -m coach --device 1 --seconds 12 --exercise ... --auto-channel
    python -m coach --device 1 --seconds 12 --exercise ... --fail-ollama
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from audio_probe.config import AudioConfig
from audio_probe.devices import find_mtrack_duo, list_input_devices
from audio_probe.stream import AudioStream

from perception.engine import PerceptionEngine
from perception.events import EventTracker, NoteEvent
from perception.sequence import compare
from perception.performance import PerformanceEvaluator
from ai.teacher import Teacher, TeacherContext, FakeLLMProvider, PolicyValidator
from ai.teacher.build_context import build_context
from ai.teacher.provider import OllamaProvider
from app.services.teacher_service import TeacherService


def _ollama_provider(model: str, fail: bool):
    if fail:
        return FakeLLMProvider(mode="unavailable")
    return OllamaProvider(model=model)


def _measure_channels(idx: int, seconds: float = 1.0) -> list:
    """Measure peak dBFS per channel before capture. Informs channel choice."""
    cfg = AudioConfig(device=idx, sample_rate=44100, block_size=1024, channels=2)
    peaks = None
    n = 0

    def _cb(indata, frames, time_info, status):
        nonlocal peaks, n
        if peaks is None:
            peaks = np.zeros(indata.shape[1])
        for ch in range(indata.shape[1]):
            peaks[ch] = max(peaks[ch], float(np.max(np.abs(indata[:, ch]))))
        n += 1

    stream = AudioStream(cfg, idx, on_meter=lambda _: None)
    base = stream._callback
    stream._callback = _cb
    stream.start()
    time.sleep(seconds)
    stream.stop()
    if peaks is None:
        return []
    return [round(20 * np.log10(float(p) + 1e-9), 1) for p in peaks]


def _pick_channel(channels_dbfs: list, requested: int, auto: bool) -> int:
    """Resolve which channel to use. Auto picks the loudest but reports it."""
    if auto:
        if not channels_dbfs:
            return 0
        best = int(np.argmax(channels_dbfs))
        return best
    # explicit: clamp to available
    if 0 <= requested < len(channels_dbfs):
        return requested
    return 0


def run_session(args) -> int:
    idx = args.device
    if idx is None:
        m = find_mtrack_duo()
        idx = m["index"] if m else None
        if idx is None:
            print("No M-Track Duo auto-detected. Use --device N.", file=sys.stderr)
            for d in list_input_devices():
                print(f"  {d['index']}: {d['name']}", file=sys.stderr)
            return 2

    # --- Load exercise ---
    try:
        from exercises.exercise import load_exercise
        ex = load_exercise(args.exercise)
    except FileNotFoundError:
        print(f"EXERCISE NOT FOUND: {args.exercise}", file=sys.stderr)
        return 2
    # Tempo is a property of the exercise (CHANGE-05). No hardcoded fallback:
    # if the exercise JSON lacks tempo, fail visibly rather than guess.
    if ex.target_bpm is None or ex.subdivision is None:
        print(f"EXERCISE MISSING TEMPO: {ex.id} (need target_bpm + subdivision)", file=sys.stderr)
        return 2
    tempo = {
        "target_bpm": ex.target_bpm,
        "subdivision": ex.subdivision,
        "start_bpm": ex.start_bpm if ex.start_bpm is not None else ex.target_bpm,
    }

    # --- Channel selection (explicit or auto-with-report) ---
    channels_dbfs = _measure_channels(idx, seconds=1.0)
    chosen = _pick_channel(channels_dbfs, args.channel, args.auto_channel)
    # Report per-channel dBFS so the user knows what carries the guitar.
    report = " | ".join(f"{i+1}: {d} dBFS" for i, d in enumerate(channels_dbfs))
    print(f"[coach] Input channels: {report}", flush=True)
    print(f"[coach] Selected channel: {chosen} "
          f"({'auto-detected' if args.auto_channel else 'explicit'})", flush=True)

    # --- Setup pipeline (stereo capture; we select the chosen channel) ---
    cfg = AudioConfig(device=idx, sample_rate=44100, block_size=1024, channels=2)
    eng = PerceptionEngine(sr=cfg.sample_rate, analysis_window=4096)
    tracker = EventTracker()
    provider = _ollama_provider(args.ollama_model, args.fail_ollama)
    policy = PolicyValidator(
        available_exercises={
            ex.id: {"start_bpm": tempo["start_bpm"], "target_bpm": tempo["target_bpm"], "enabled": True, "prerequisites": []},
        }
    )
    teacher = Teacher(provider=provider, policy=policy)

    raw_events: list = []
    note_events: list = []
    blocks = 0
    max_peak = 0.0
    stream = AudioStream(cfg, idx, on_meter=lambda _: None)
    base_cb = stream._callback

    def _cb(indata, frames, time_info, status):
        nonlocal blocks, max_peak
        block = indata[:, chosen] if indata.shape[1] > chosen else indata.ravel()
        blocks += 1
        pk = float(np.max(np.abs(block)))
        max_peak = max(max_peak, pk)
        ev = eng.process_block(block)
        if ev is not None:
            raw_events.append(ev)
            closed = tracker.process(ev)
            if closed is not None:
                note_events.append(closed)
        base_cb(indata, frames, time_info, status)

    stream._callback = _cb
    print(f"[coach] capturing {args.seconds}s on device {idx} | exercise={ex.id} | fail_ollama={args.fail_ollama}", flush=True)
    t0 = datetime.now(timezone.utc).isoformat()
    stream.start()
    time.sleep(args.seconds)
    stream.stop()
    t1 = datetime.now(timezone.utc).isoformat()

    if note_events:
        for ne in tracker.finalize():
            note_events.append(ne)

    # --- MVP-3: compare ---
    comp = compare(ex.id, ex.expected_sequence, note_events)
    # --- MVP-4: evaluate ---
    perf = PerformanceEvaluator().evaluate(
        comp, target_bpm=tempo["target_bpm"], subdivision=tempo["subdivision"],
        performed_bpm=TeacherService._estimate_bpm(note_events, tempo["subdivision"], tempo["target_bpm"]),
    )
    # --- MVP-5: teacher decision ---
    ctx = build_context(
        student_profile={"experience": args.student, "goals": ["rock"], "practice_minutes": 30},
        exercise={"id": ex.id, "start_bpm": tempo["start_bpm"], "target_bpm": tempo["target_bpm"]},
        performance=perf,
        available_exercises=[ex.id],
        voice_mode="COACH",
    )
    ctx.rendered = json.dumps(ctx.to_dict(), ensure_ascii=False)
    decision = teacher.decide(ctx)
    decision_dict = {
        "accepted": decision.accepted,
        "action": decision.action,
        "exercise_id": decision.exercise_id,
        "tempo": decision.tempo,
        "reason": decision.reason,
        "spoken_feedback": decision.spoken_feedback,
        "source": decision.source,
        "model": getattr(provider, "model", None) if not args.fail_ollama else None,
    }

    # --- Write artifacts ---
    out = Path(args.session)
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.json").write_text(json.dumps({
        "session": out.name,
        "exercise_id": ex.id,
        "exercise_name": ex.name,
        "device": idx,
        "seconds": args.seconds,
        "fail_ollama": args.fail_ollama,
        "channels_dbfs": channels_dbfs,
        "selected_channel": chosen,
        "started_utc": t0,
        "ended_utc": t1,
        "blocks": blocks,
        "max_peak": max_peak,
        "max_peak_dbfs": 20 * np.log10(max_peak + 1e-9),
        "raw_events": len(raw_events),
        "note_events": len(note_events),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "performance.json").write_text(json.dumps({
        "performance": perf.to_dict(),
        "alignment": comp.to_dict(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "teacher_decisions.json").write_text(json.dumps({
        "teacher_context": ctx.to_dict(),
        "decision": decision_dict,
        "ollama_failed": args.fail_ollama,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "notes.md").write_text(_notes_template(ex, perf, decision_dict, args, channels_dbfs, chosen), encoding="utf-8")

    # --- Console summary ---
    print("\n=== PERFORMANCE (MVP-4) ===")
    print(json.dumps(perf.to_dict(), indent=2))
    print("\n=== TEACHER DECISION (MVP-5) ===")
    print(json.dumps(decision_dict, indent=2, ensure_ascii=False))
    print(f"\n[coach] artifacts written to {out.resolve()}")
    return 0


def _notes_template(ex, perf, decision: dict, args, channels_dbfs, chosen) -> str:
    p = perf.to_dict()
    ch_report = " | ".join(f"{i+1}: {d} dBFS" for i, d in enumerate(channels_dbfs))
    return f"""# Validation Session — {ex.name} ({ex.id})

## Audio
- channels (dBFS): {ch_report}
- selected: {ch_report.split(' | ')[chosen] if channels_dbfs else 'n/a'} (channel {chosen})

## What I intended
(exercise: {ex.id}; target_bpm={p.get('target_bpm')})

## What I played
(FILL MANUALLY: e.g. "played scale clean and slow")

## What system detected
- note_accuracy: {p['note_accuracy']}
- timing_accuracy: {p['timing_accuracy']}
- uncertain_ratio: {p['uncertain_ratio']}
- performed_bpm: {p['performed_bpm']} (target {p['target_bpm']})
- mean_timing_error_ms: {p['mean_timing_error_ms']}
- counts: {p['counts']}

## What teacher decided
- action: {decision['action']} (accepted={decision['accepted']}, source={decision['source']})
- tempo: {decision['tempo']}
- reason: {decision['reason']}
- spoken: {decision['spoken_feedback']}

## What felt wrong
(FILL MANUALLY: any pedagogical mismatch, crash, nonsense feedback)

## Session config
- device: {args.device}
- seconds: {args.seconds}
- fail_ollama: {args.fail_ollama}
- channel: {chosen} ({'auto' if args.auto_channel else 'explicit'})
"""


def main() -> int:
    p = argparse.ArgumentParser(description="Local Guitar Coach — full-stack validation MVP-0..MVP-5")
    p.add_argument("--device", type=int, default=None)
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--exercise", type=str, default="exercises/scale_e_minor_001.json")
    p.add_argument("--session", type=str, default="validation/session_001")
    p.add_argument("--student", type=str, default="beginner")
    p.add_argument("--ollama-model", type=str, default="qwen2.5:7b")
    p.add_argument("--fail-ollama", action="store_true", help="simulate Ollama down (Test 6)")
    p.add_argument("--channel", type=int, default=0, help="audio channel to use (0 or 1); ignored if --auto-channel")
    p.add_argument("--auto-channel", action="store_true", help="auto-select loudest channel (reported, not silent)")
    args = p.parse_args()
    return run_session(args)


if __name__ == "__main__":
    raise SystemExit(main())
