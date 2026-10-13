"""Unit tests for MVP-0 — no audio hardware required.

Hardware smoke test lives in tests/test_hardware_smoke.py (skipped unless
--hardware is passed).
"""
import numpy as np
import pytest

from audio_probe.config import AudioConfig
from audio_probe.devices import (
    filter_by_host_api,
    find_device_by_substring,
    find_mtrack_duo,
    resolve_device,
)
from audio_probe.meters import LevelMeter, dbfs_peak, dbfs_rms, peak, rms, to_dbfs
from audio_probe.waveform import WaveformBuffer


# ---- config ----

def test_config_defaults():
    c = AudioConfig()
    assert c.channels == 1
    assert c.sample_rate == 44100
    c.validate()  # must not raise


def test_config_invalid_channels():
    with pytest.raises(ValueError):
        AudioConfig(channels=3).validate()


def test_config_roundtrip_dict():
    c = AudioConfig(device=2, channels=2, sample_rate=48000, block_size=512)
    c.validate()
    assert AudioConfig.from_dict(c.to_dict()) == c


# ---- meters ----

def test_rms_sine():
    x = np.sin(2 * np.pi * np.linspace(0, 1, 1000))
    # RMS of a unit sine is 1/sqrt(2); discrete sampling error ~1e-3
    assert abs(rms(x) - (1 / np.sqrt(2))) < 2e-3


def test_rms_square_exact():
    x = np.tile([1.0, -1.0], 500)
    assert abs(rms(x) - 1.0) < 1e-9


def test_peak_and_dbfs():
    x = np.array([0.0, 0.5, -0.5, 0.0])
    assert peak(x) == 0.5
    assert dbfs_peak(x) == to_dbfs(0.5)
    assert dbfs_rms(np.zeros(10)) == float("-inf")


def test_level_meter_smoothing():
    m = LevelMeter(smoothing=0.5, peak_hold_decay=0.0)
    r1 = m.update(np.full(100, 1.0))
    r2 = m.update(np.zeros(100))
    # peak hold decays to 0 with decay=0
    assert r2["peak_hold"] == 0.0
    # rms smoothed (alpha=0.5): first -> 0.5, second -> 0.25
    assert r1["rms"] == 1.0
    assert r2["rms_smoothed"] == 0.25


def test_level_meter_invalid_smoothing():
    with pytest.raises(ValueError):
        LevelMeter(smoothing=1.5)


# ---- waveform ----

def test_waveform_linear():
    w = WaveformBuffer(8)
    w.push(np.arange(5))
    w.push(np.arange(5, 10))
    # capacity 8 keeps only the last 8 samples: [2,3,4,5,6,7,8,9]
    np.testing.assert_array_equal(w.snapshot(), np.arange(2, 10))


def test_waveform_wraparound():
    w = WaveformBuffer(4)
    w.push(np.array([1.0, 2.0, 3.0, 4.0]))
    w.push(np.array([5.0, 6.0]))  # wraps
    np.testing.assert_array_equal(w.snapshot(), [3.0, 4.0, 5.0, 6.0])


def test_waveform_oversize_block():
    w = WaveformBuffer(4)
    w.push(np.array([10.0, 20.0, 30.0, 40.0, 50.0]))
    np.testing.assert_array_equal(w.snapshot(), [20.0, 30.0, 40.0, 50.0])


def test_waveform_empty():
    w = WaveformBuffer(4)
    assert w.snapshot().shape == (4,)


# ---- devices (pure, with fake lists) ----

_FAKE_DEVICES = [
    {"index": 0, "name": "Mapeador de sons - Input", "max_input_channels": 2,
     "host_api": "MME", "is_default": False},
    {"index": 1, "name": "Line 1/2 (9- M-Audio M-Track Solo and Duo)", "max_input_channels": 2,
     "host_api": "MME", "is_default": True},
    {"index": 25, "name": "Line 1/2 (9- M-Audio M-Track Solo and Duo)", "max_input_channels": 2,
     "host_api": "Windows WASAPI", "is_default": False},
    {"index": 34, "name": "Line 1/2 (M-Track Solo and Duo In 1-2)", "max_input_channels": 2,
     "host_api": "Windows WDM-KS", "is_default": False},
]


def test_filter_by_host_api():
    mme = filter_by_host_api(_FAKE_DEVICES, "MME")
    assert all(d["host_api"] == "MME" for d in mme)
    assert len(mme) == 2


def test_find_mtrack_duo():
    found = find_mtrack_duo(_FAKE_DEVICES)
    assert found is not None
    assert "M-Track" in found["name"]


def test_find_device_by_substring_prefers_default():
    found = find_device_by_substring("line 1/2", _FAKE_DEVICES)
    assert found["index"] == 1  # default match wins


def test_resolve_explicit_device(monkeypatch):
    # Portable: do not depend on the real machine's device index.
    monkeypatch.setattr(
        "audio_probe.devices.list_input_devices", lambda: _FAKE_DEVICES
    )
    # Device 1 is a valid input in the fake list.
    assert resolve_device(config_device=1, host_api=None) == 1
    # Device 25 (also present in fakes) resolves too.
    assert resolve_device(config_device=25, host_api=None) == 25


def test_resolve_explicit_invalid_raises():
    with pytest.raises(ValueError):
        resolve_device(config_device=999, host_api=None)


def test_resolve_autodetect_mtrack(monkeypatch):
    # Mock device list: indices change per host API on real hardware, so the
    # test must not depend on the machine's actual devices.
    import audio_probe.devices as devmod
    mock = [
        {"index": 0, "name": "Microsoft Sound Mapper - Input", "max_input_channels": 2,
         "default_sample_rate": 44100.0, "host_api": "MME", "is_default": False},
        {"index": 1, "name": "Line (M-Audio M-Track Duo)", "max_input_channels": 2,
         "default_sample_rate": 44100.0, "host_api": "MME", "is_default": False},
        {"index": 7, "name": "Microphone (Realtek Audio)", "max_input_channels": 2,
         "default_sample_rate": 44100.0, "host_api": "Windows WASAPI", "is_default": True},
    ]
    monkeypatch.setattr(devmod, "list_input_devices", lambda: mock)
    idx = resolve_device(config_device=None, host_api=None)
    assert idx == 1
