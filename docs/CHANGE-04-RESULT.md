# CHANGE-04 — RIFF: P2-A (cents) + P2-B (meter semantics) RESULT

**Status: CLOSED** (P2-A implemented, P2-B document-only, meter NOT unified)

## READ-FIRST (evidence)
- `app/models/session.py:36` — `PitchTelemetry.cents: Optional[float]` exists (schema).
- `app/services/session_service.py:148-157` — `_make_pitch_callback` did NOT emit `cents`.
- `frontend/app.js:288-293` — `setCents(cents)` already renders the tuner; `:306` calls
  `setCents(data.cents ?? null)`. Frontend was ready; backend was missing the field.
- `perception/notes.py:12-19` — `freq_to_midi()` exists (read-only, not modified).
- `app/api/websocket.py:104-108` — setup sends `channels_dbfs`/`meter_message` (CH1/CH2);
  `session_service.py:180-188` runtime sends `meter` (rms_db/peak_db of selected channel).

## P2-A — cents now emitted (IMPLEMENTED)
Chain under test (all proven):
```
frequency -> freq_to_midi() -> midi_frac -> round(midi_frac) [nearest note]
   -> cents = 100*(midi_frac - round(midi_frac))  ∈ [-50, +50]
   -> pitch websocket -> app.js setCents() -> TUNER
```
- **File changed:** `app/services/session_service.py` — `_make_pitch_callback` now computes
  `cents` from `freq_to_midi(ev.frequency)` and includes it in the `pitch` dict.
- Added `from perception.notes import freq_to_midi` (read-only import; perception core untouched).
- `cents` is `None` when frequency is missing/non-positive (safe).
- **Frontend NOT changed** (already consumed cents).

## P2-B — meter semantics DOCUMENTED (not unified)
Two intentional representations, both consumed by the frontend:
- **SETUP/diagnosis:** `channels_dbfs` (CH1/CH2 via `measure_channels`) + `meter_message`.
- **RUNTIME/session:** `meter` (`rms_db`/`peak_db` of the selected channel).
- `app.js:313-323` handles all three families (`data.rms_db ?? data.ch1`, `channels_dbfs`,
  `meter_message`). NOT a rendering bug — different intent. **Not unified** (per Dan: would
  risk websocket/callback/CH1-CH2/frontend/tests without a clear functional need).

## TEST
- New `tests/test_change04.py` (10 tests): cents A4/440=0, 441≈+3.9, 439≈-3.9, bounded ±50,
  pitch callback emits cents, PitchTelemetry accepts cents, app.js consumes cents,
  app.js consumes all meter families, meter callback emits rms+peak, perception/audio_probe untouched.
- **RED→GREEN:** `test_pitch_callback_emits_cents` failed before the change, passes after.
- Full suite: **96 passed, 1 skipped** (86 prior + 10 new). No regression.

## RE-AUDIT
- **P2-A PASS:** cents emitted in `pitch`; tuner no longer inert. Frontend untouched.
- **P2-B PASS (document-only):** meter semantics preserved; not unified.
- **`perception/` untouched:** `git diff --name-only` shows NO perception/ files modified.
- **`audio_probe/stream.py` untouched:** not in `git diff --name-only`. P2-D remains blocked
  (physical/USB validation), out of scope.
- **`node --check frontend/app.js` + `neck.js`:** OK.

## REGRESSION
- Full suite green (96 passed, 1 skipped). No regression.

## ROLLBACK
- Revert `app/services/session_service.py` `_make_pitch_callback` to the pre-change version
  (remove cents computation + the `freq_to_midi` import).
- Remove `tests/test_change04.py`.
- No migration, no perception/ change.

## STATUS
- **CHANGE-04 (RIFF): CLOSED** — P2-A implemented, P2-B documented, meter not unified.
- **CHANGE-05 (RIFF, P2-C tempo/BPM single source): NOT STARTED**
- **CHANGE-06 (RIFF, P2-D audio channel routing): NOT STARTED** (blocked on physical/USB validation)
- **MVP-6: still OPEN** (gate §4 not fully proven — this change is a backlog item, not the gate)