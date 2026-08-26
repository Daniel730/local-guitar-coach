"""Hardware smoke test for MVP-0.

Skipped unless --hardware is passed (so `pytest` alone runs fast with no
audio device). Play a note into the M-Track Duo while this runs.

Run:  pytest tests/test_hardware_smoke.py --hardware -s
"""
import pytest

from audio_probe.meters import to_dbfs
from audio_probe.probe import AudioProbe


@pytest.mark.hardware
def test_hardware_captures_signal():
    probe = AudioProbe()
    result = probe.run(seconds=3.0)
    print("\nProbe result:", result)
    assert result.blocks_received > 0, "no audio blocks arrived"
    assert result.detected, "device reported but no signal detected"
    # With guitar plugged in and a note played, we expect some level.
    assert result.max_peak >= 0.0
    print(f"max peak: {result.max_peak:.4f} ({to_dbfs(result.max_peak):.1f} dBFS)")
