# Local Guitar Coach — codename: Riff

Local, adaptive, data-driven guitar teacher with voice interaction.
Target: Windows + M-Audio M-Track Duo + Ollama. See `docs/PROJECT_STATE.md` (canonical).

## Current state

**MVP-0 — Audio Probe** (the first link in the chain):

```
M-Track Duo -> Windows -> Python -> Audio captured successfully
```

This repo implements **MVP-0 through MVP-5** (see `docs/PROJECT_STATE.md`).
**MVP-6 (Web App)** is OPEN — gated on the acceptance criteria in `PROJECT_STATE.md` §4.
Per the contract schema, MVP-6 verifies the full server-side capture →
perception → teacher → telemetry → browser path before any new feature work.

## Layout

```
local-guitar-coach/
├── audio_probe/      # MVP-0: device, config, stream, meters, waveform, probe, cli
├── tests/            # unit tests (no hardware) + hardware smoke test (gated)
├── conftest.py
├── pytest.ini
└── README.md
```

## Requirements

- Windows (tested on the M-Track Duo target)
- Python 3.11 with `sounddevice`, `numpy`, `pytest`

Install deps (already present in this environment):
```
pip install sounddevice numpy pytest
```

## Usage

List input devices:
```
python -m audio_probe --list
```

Probe 3 seconds on the auto-selected device:
```
python -m audio_probe --seconds 3
```

Force a device index (see `--list`):
```
python -m audio_probe --device 1 --seconds 3
```

## Tests

Unit tests (no audio hardware needed):
```
pytest
```

Hardware smoke test (needs the M-Track Duo; play a note during capture):
```
pytest tests/test_hardware_smoke.py --hardware -s
```

## Definition of Done (ARCH §27)

Each feature needs: Implementation + Unit Tests + Integration Test +
Error Handling + Documentation + Manual Smoke Test. MVP-0 satisfies this
for the audio-capture link.
