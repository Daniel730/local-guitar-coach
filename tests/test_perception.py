"""Deterministic tests for the MVP-1 Perception Engine.

No sound card required: pitch is validated against synthesized sine waves
whose true frequency is known exactly.
"""
import math
import numpy as np
import pytest

from perception.notes import freq_to_midi, midi_to_note, freq_to_note
from perception.pitch import yin_estimate
from perception.onset import OnsetDetector
from perception.engine import PerceptionEngine, MusicalEvent


# --- note conversion ---
def test_freq_to_midi_a4():
    assert abs(freq_to_midi(440.0) - 69.0) < 1e-9


def test_freq_to_midi_e2():
    # E2 = 82.4069 Hz -> MIDI 40
    assert abs(freq_to_midi(82.4069) - 40.0) < 1e-3


def test_midi_to_note_boundary():
    assert midi_to_note(40) == "E2"
    assert midi_to_note(69) == "A4"
    assert midi_to_note(60) == "C4"


def test_freq_to_note_e2():
    note, midi = freq_to_note(82.41)
    assert note == "E2"
    assert midi == 40


def test_freq_to_note_invalid():
    assert freq_to_note(0.0) == (None, None)
    assert freq_to_note(-5.0) == (None, None)


# --- YIN on real sines ---
def _sine(freq, sr=44100, dur=0.5, amp=0.5):
    t = np.arange(int(sr * dur)) / sr
    return amp * np.sin(2 * math.pi * freq * t)


def test_yin_recovers_low_e():
    x = _sine(82.41, dur=0.5)
    f, conf = yin_estimate(x, 44100, fmin=40, fmax=2000)
    assert f is not None
    assert abs(f - 82.41) < 1.0  # within ~1 Hz
    assert conf > 0.8


def test_yin_recovers_a440():
    x = _sine(440.0, dur=0.3)
    f, conf = yin_estimate(x, 44100, fmin=40, fmax=2000)
    assert f is not None
    assert abs(f - 440.0) < 2.0
    assert conf > 0.8


def test_yin_rejects_noise():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.3, 44100 // 10)
    f, conf = yin_estimate(x, 44100, fmin=40, fmax=2000)
    assert conf < 0.5  # noise -> low confidence


def test_yin_short_frame_returns_none():
    x = np.zeros(2)
    f, conf = yin_estimate(x, 44100)
    assert f is None


# --- onset ---
def test_onset_fires_on_rise():
    od = OnsetDetector(threshold_db=-45.0, refractory_s=0.05)
    assert od.update(-60.0, 0.0) is False
    assert od.update(-40.0, 0.01) is True
    # still high -> no new onset
    assert od.update(-40.0, 0.02) is False


# --- engine end-to-end on synthesized sequence ---
def test_engine_emits_two_onsets():
    sr = 44100
    eng = PerceptionEngine(sr=sr, analysis_window=4096)
    blocks = []
    # E2 0.4s
    blocks.append(_sine(82.41, sr, dur=0.4))
    # silence 0.3s
    blocks.append(np.zeros(int(sr * 0.3)))
    # A2 (110 Hz) 0.4s
    blocks.append(_sine(110.0, sr, dur=0.4))

    events = []
    t = 0.0
    for b in blocks:
        ev = eng.process_block(b, timestamp=t)
        if ev is not None:
            events.append(ev)
        t += b.size / sr

    onsets = [e for e in events if e.onset]
    notes = {e.note for e in events}
    assert "E2" in notes
    assert "A2" in notes
    assert len(onsets) >= 2  # at least one onset per note group


def test_musical_event_to_dict_rounds():
    ev = MusicalEvent(
        timestamp=1.247, frequency=82.41, note="E2", midi=40,
        confidence=0.97, amplitude=0.73, onset=True,
    )
    d = ev.to_dict()
    assert d["note"] == "E2"
    assert d["midi"] == 40
    assert round(d["frequency"], 2) == 82.41
