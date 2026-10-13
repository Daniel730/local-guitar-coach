# HARDWARE SIGNAL TEST — MVP-6 blocker

**Date:** 2026-08-26
**Interface:** M-Audio M-Track Duo
**PC device:** 1 (MME, 44100 Hz, 2ch)
**Tool:** audio_probe (stereo, no channel selection, no gain change, no YIN)

## PC-measured levels (from diagnostic run, agent-observed)

| Phase        | CH1        | CH2        |
|--------------|------------|------------|
| silence      | -55.0 dBFS | -50.9 dBFS |
| guitar       | -52.1 dBFS | -51.0 dBFS |
| strong guitar| -44.7 dBFS | -51.1 dBFS |

Both channels stay at the noise floor. Playing the guitar (normal OR strong) produced NO
audible rise in either channel. Reference working level from earlier MVP-1 live run: -11 dBFS.

## Fields requiring USER physical inspection (agent cannot observe)

| Field            | State                |
|------------------|----------------------|
| CH2 cable        | USER REPORT          |
| INST (CH2)       | USER REPORT          |
| GAIN (CH2)       | USER REPORT          |
| Direct monitoring| USER REPORT (A/B)    |
| LED/meter        | USER REPORT          |
| Cable            | USER REPORT          |
| Guitar           | USER REPORT          |

## PC CH1 / PC CH2 (agent-measured baseline)

- PC CH1: ≈ -44 to -55 dBFS (noise floor, no signal)
- PC CH2: ≈ -51 dBFS (noise floor, no signal)

## Conclusion (so far)

SIGNAL ABSENT at PC input. Software pipeline (capture, channel report, Ollama, fallback) is
verified working independently. The guitar signal is not reaching the M-Track / PC. This is a
physical input problem (cable / INST / gain / input selection), NOT a code defect.

MVP-6 remains blocked until: silence ≈ noise floor AND guitar ≫ noise floor (YIN can detect notes).
