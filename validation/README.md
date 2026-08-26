# Full-Stack Validation — MVP-0 → MVP-5 (Adversarial)

**Goal:** prove the ENTIRE chain works with a real guitar before adding STT/TTS.
**Rule:** no "pretty" session. Break it on purpose.

## Prereqs (one time)
```
cd C:\Users\Danie\local-guitar-coach
.\.venv\Scripts\Activate.ps1
python -m pytest -q            # must be 72 passed
```

## The 6 adversarial tests

Run each with the command below, then open `validation/session_00X/notes.md`
and fill the MANUAL sections (What I intended / played / felt wrong).

Device is the M-Track Duo index (usually `1`). Tune `--seconds` to your playing.

---

### Test 1 — correct, slow & clean
Exercise: scale_e_minor_001 (E G A B D E). Play it slowly and cleanly.
```powershell
python -m coach --device 1 --seconds 14 `
  --exercise exercises/scale_e_minor_001.json `
  --session validation/session_001 --student beginner
```
Expect: note_accuracy≈1.0, timing_accuracy depends, Teacher ACCEPT/REPEAT.

### Test 2 — deliberately wrong
Same exercise, but play: **E F# C B A E** (wrong notes on purpose).
```powershell
python -m coach --device 1 --seconds 14 `
  --exercise exercises/scale_e_minor_001.json `
  --session validation/session_002 --student beginner
```
Expect: alignment shows `wrong`/`missing`/`extra`; Teacher must NOT say "speed up".

### Test 3 — right notes, BAD timing
Play the right notes but rush/ drag them off the beat.
```powershell
python -m coach --device 1 --seconds 14 `
  --exercise exercises/scale_e_minor_001.json `
  --session validation/session_003 --student beginner
```
Expect: note_accuracy high, timing_accuracy LOW, mean_timing_error_ms up;
Teacher reasons about TIMING (not blind "notes ok → speed up").

### Test 4 — under tempo
Exercise target=100 BPM. Play at ~70–80 BPM, right notes.
```powershell
python -m coach --device 1 --seconds 14 `
  --exercise exercises/scale_e_minor_001.json `
  --session validation/session_004 --student beginner
```
Expect: performed_bpm≈75, NOT auto-failed. tempo_ratio<1, no penalty in decision.

### Test 5 — good, good, bad (consistency)
Run Test 1 twice (excellent), then once sloppy. We aggregate attempts.
```powershell
python -m coach --device 1 --seconds 14 --exercise exercises/scale_e_minor_001.json --session validation/session_005a
python -m coach --device 1 --seconds 14 --exercise exercises/scale_e_minor_001.json --session validation/session_005b
python -m coach --device 1 --seconds 14 --exercise exercises/scale_e_minor_001.json --session validation/session_005c
```
Then check the SkillState: `trend` must NOT be `declining` from one outlier
(needs ≥3 obs; the 3rd bad run alone is `insufficient_data`/`stable`).

### Test 6 — kill Ollama (REQUIRED)
Start Ollama, then KILL it before the decision:
```powershell
# in a separate terminal, if Ollama is running:
#   ollama stop     (or close the Ollama app)
python -m coach --device 1 --seconds 14 `
  --exercise exercises/scale_e_minor_001.json `
  --session validation/session_006 --student beginner --fail-ollama
```
`--fail-ollama` simulates Ollama down. Expect: Performance completes,
Teacher → deterministic FALLBACK (REPEAT), session continues, artifacts saved.

(Ollama is only needed if you want the REAL brain; the FakeLLM path is also
covered by the test suite. For a true Ollama run, drop `--fail-ollama` and
ensure `ollama` python pkg + a model are installed.)

---

## Artifacts written per session
```
validation/session_00X/
  session.json          # device, blocks, peak dBFS, counts
  performance.json      # PerformanceResult + alignment
  teacher_decisions.json# context + decision + source (llm/fallback/policy_fail)
  notes.md              # MANUAL: intended / played / detected / decided / felt wrong
```

## Red flags to watch (write in notes.md)
- Teacher says "increase BPM" when timing_accuracy is low → pedagogical mismatch.
- Any crash / hang in the live path (the unit tests can't catch these).
- Performed BPM wildly wrong (estimator is crude — flag it).
- Ollama fallback not triggering when killed.

## Pass criterion
All 6 sessions produce valid artifacts AND the decisions are pedagogically
defensible (no blind speed-up on bad timing; fallback works when Ollama dies).
If green → core is Alpha-ready → proceed to MVP-6 (voice).
