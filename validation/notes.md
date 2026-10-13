# Real Session Validation — MVP-0 → MVP-5 (Adversarial)

**Date:** 2026-08-26
**Device:** M-Track Duo (index 1, MME stereo)
**Model:** llama3.1:8b (Ollama, localhost:11434)
**Exercise:** scale_e_minor_001 (E G A B D E), target_bpm=100

## CRITICAL OBSERVATION (not edited, reported as-is)

In ALL 8 sessions the detected audio was near-silence:
- Channel levels measured before capture: ~ -50 to -55 dBFS (channel 1), ~ -50 dBFS (channel 2).
- During TEST 5a channel 1 briefly reached -42 dBFS (some signal present) but still 0 notes detected.
- A played guitar should read -11 to -15 dBFS (as seen in earlier MVP-1 live runs).

**Result:** `note_accuracy = 0.0` and `counts.missing = 6` in every session. The guitar signal
did NOT reach the PC during this validation run (cable/volume/input-select issue, same class
of problem seen at the very start of the project). The Ollama/Teacher pipeline still produced
valid decisions because it reasons from the (empty) performance context.

This is NOT a code defect in MVP-0..MVP-5 — the audio capture/selection works (levels are
reported, stream runs, no crash). It is a hardware/setup state: no usable guitar signal.

## What was validated GREEN (independent of the silent input)

- **Channel selection explicit & reported:** every run printed `Input channels: 1: X | 2: Y`
  and `Selected channel: 1 (explicit)`. No silent auto-detection. ✅
- **Ollama real → decision → schema → policy → ACCEPT:** tests 1–5 all `source=llama3.1:8b`,
  valid action SLOW_DOWN, schema-valid JSON, policy-accepted. ✅
- **Fallback (TEST 6):** `source=fallback`, action=REPEAT, session continued, artifacts saved. ✅
- **No crashes / no unexpected exits** in any of the 8 runs. ✅
- **All 8 sessions persisted** teacher_decisions.json + performance.json + session.json + notes.md. ✅

## Per-session

| Test | source | model | action | tempo | note_acc | levels (ch1/ch2) |
|------|--------|-------|--------|-------|----------|------------------|
| 1 | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -54.5 / -50.8 |
| 2 | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -53.5 / -51.2 |
| 3 | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -55.2 / -51.2 |
| 4 | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -55.2 / -51.2 |
| 5a | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -42.2 / -51.2 |
| 5b | llm | llama3.1:8b | SLOW_DOWN | 80 | 0.0 | -52.5 / -51.2 |
| 5c | llm | llama3.1:8b | SLOW_DOWN | null | 0.0 | -53.8 / -50.8 |
| 6 | fallback | None | REPEAT | 90.0 | 0.0 | -54.1 / -50.9 |

## Teacher feedback contextuality (IMPROVEMENT, not blocker)

The Ollama reasoning correctly referenced the measured state (e.g. "note accuracy and timing
accuracy are both 0"). However the spoken_feedback was generic ("let's slow down and focus on
playing each note cleanly") rather than grounding in the specific numbers. This is the same
IMPROVEMENT noted in the V2 analysis: spoken feedback should anchor in the measured evidence.
Not a pipeline blocker.

## What needs to happen before MVP-6 can be truly validated

1. Guitar signal must reach the PC at usable level (-11 to -15 dBFS). Re-check:
   cable in Channel 2 (Hi-Z Instrument) of M-Track, input selector, gain knob, guitar volume.
2. Then re-run the 6 tests. With real notes, we can finally verify:
   - note_accuracy / timing_accuracy are meaningful
   - alignment wrong/missing/extra works on real playing
   - Teacher reasons about REAL timing errors (not just "accuracy is 0")
3. Fallback REAL (kill daemon) remains UNVERIFIED — only the simulated path was tested.
   Unit coverage exists (test_ollama_unavailable_fallback).
