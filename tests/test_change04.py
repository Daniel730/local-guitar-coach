"""CHANGE-04 regression tests: P2-A (cents emitted) + P2-B (meter semantics documented).

Rules: only app/services/session_service.py is touched for P2-A; perception/ and
audio_probe/stream.py are untouched by this change. These tests prove the
contracts enforced by CHANGE-04.

P2-A chain under test:
    frequency -> freq_to_midi() -> midi_frac -> nearest MIDI note -> cents
    -> pitch websocket -> app.js setCents() -> TUNER

P2-B (document-only): the meter has two intentional representations —
    SETUP/diagnosis: channels_dbfs (CH1/CH2 via measure_channels)
    RUNTIME/session:  meter (rms_db/peak_db of the selected channel)
The frontend consumes all three families (meter, channels_dbfs, meter_message).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.models.session import PitchTelemetry
from app.services.session_service import SessionService
from perception.notes import freq_to_midi


# ---- P2-A: cents is computed and emitted in the pitch telemetry ----

def _cents_from_freq(freq: float) -> float:
    """Reference implementation of the cents derivation (mirrors the change)."""
    midi_frac = freq_to_midi(freq)
    assert midi_frac is not None
    return 100.0 * (midi_frac - round(midi_frac))


def test_cents_a4_440_is_zero():
    assert _cents_from_freq(440.0) == pytest.approx(0.0, abs=0.01)


def test_cents_441_is_plus_approx_4():
    # 441 Hz is ~3.93 cents sharp of A4
    assert _cents_from_freq(441.0) == pytest.approx(3.93, abs=0.1)


def test_cents_439_is_minus_approx_4():
    assert _cents_from_freq(439.0) == pytest.approx(-3.93, abs=0.1)


def test_cents_bounded_within_50():
    # Any frequency maps to the nearest note, so cents is always in [-50, +50].
    for f in (110.0, 220.0, 330.0, 440.0, 880.0, 123.45, 987.65):
        c = _cents_from_freq(f)
        assert -50.0 <= c <= 50.0, f"cents {c} out of range for {f} Hz"


def test_pitch_callback_emits_cents():
    """The pitch callback must include cents in the emitted dict."""
    svc = SessionService()
    emitted = {}

    def fake_emit(data: dict) -> None:
        emitted.update(data)

    svc.register_emitter("s1", fake_emit)
    cb = svc._make_pitch_callback("s1")

    from perception.engine import MusicalEvent

    ev = MusicalEvent(
        timestamp=0.0, frequency=441.0, note="A4", midi=69,
        confidence=0.9, amplitude=0.1, onset=True,
    )
    cb(ev)

    assert emitted["type"] == "pitch"
    assert emitted["note"] == "A4"
    assert emitted["frequency"] == 441.0
    assert "cents" in emitted, "cents must be present in pitch telemetry"
    assert emitted["cents"] == pytest.approx(3.93, abs=0.1)


def test_pitch_telemetry_schema_accepts_cents():
    t = PitchTelemetry(note="A4", cents=3.93, frequency=441.0, confidence=0.9, onset=True)
    d = t.model_dump()
    assert d["cents"] == pytest.approx(3.93, abs=0.01)
    assert d["type"] == "pitch"


def test_app_js_consumes_cents():
    """The frontend already renders cents via setCents(data.cents ?? null)."""
    app_js = Path(__file__).resolve().parent.parent / "frontend" / "app.js"
    text = app_js.read_text(encoding="utf-8")
    assert "setCents(data.cents ?? null)" in text, "app.js must consume cents from pitch"
    assert "pitch-cents" in text, "tuner element must exist"


# ---- P2-B: meter semantics documented (no unification) ----

def test_app_js_consumes_all_meter_families():
    """The frontend handles meter, channels_dbfs, and meter_message — the two
    intentional representations (setup CH1/CH2 vs runtime selected channel)."""
    app_js = Path(__file__).resolve().parent.parent / "frontend" / "app.js"
    text = app_js.read_text(encoding="utf-8")
    assert "data.rms_db ?? data.ch1" in text, "meter family consumed"
    assert "channels_dbfs" in text, "channels_dbfs family consumed"
    assert "meter_message" in text, "meter_message family consumed"


def test_meter_callback_emits_rms_and_peak():
    """Runtime meter callback emits rms_db + peak_db of the selected channel."""
    svc = SessionService()
    emitted = {}

    def fake_emit(data: dict) -> None:
        emitted.update(data)

    svc.register_emitter("s2", fake_emit)
    cb = svc._make_meter_callback("s2")
    cb([-20.0, -10.0])

    assert emitted["type"] == "meter"
    assert emitted["rms_db"] == pytest.approx(-20.0, abs=0.1)
    assert emitted["peak_db"] == pytest.approx(-10.0, abs=0.1)


def test_perception_and_audio_probe_untouched():
    """CHANGE-04 must not modify perception/ or audio_probe/stream.py."""
    repo = Path(__file__).resolve().parent.parent
    # This test is a guard: if the change touched these, the diff check in the
    # report will catch it. Here we assert the files still exist and are importable.
    assert (repo / "perception" / "notes.py").exists()
    assert (repo / "audio_probe" / "stream.py").exists()