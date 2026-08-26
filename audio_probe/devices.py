"""Device discovery and input selection.

Pure functions over the sounddevice query API so they are unit-testable
with a fake device list (no hardware required).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import sounddevice as sd


def list_input_devices() -> List[Dict]:
    """Return all input-capable devices with a normalized dict shape."""
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    result: List[Dict] = []
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue
        ha = "unknown"
        if 0 <= dev["hostapi"] < len(host_apis):
            ha = host_apis[dev["hostapi"]]["name"]
        result.append(
            {
                "index": idx,
                "name": dev["name"],
                "max_input_channels": dev["max_input_channels"],
                "default_sample_rate": dev.get("default_samplerate"),
                "host_api": ha,
                "is_default": idx == sd.default.device[0],
            }
        )
    return result


def filter_by_host_api(devices: List[Dict], host_api: Optional[str]) -> List[Dict]:
    if not host_api:
        return devices
    return [d for d in devices if d["host_api"].lower() == host_api.lower()]


def find_device_by_substring(
    substring: str, devices: Optional[List[Dict]] = None
) -> Optional[Dict]:
    devices = devices if devices is not None else list_input_devices()
    sub = substring.lower()
    matches = [d for d in devices if sub in d["name"].lower()]
    if not matches:
        return None
    for d in matches:
        if d["is_default"]:
            return d
    return matches[0]


def find_mtrack_duo(devices: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Best-effort auto-detection of the M-Audio M-Track Duo (ARCH sec. 25)."""
    devices = devices if devices is not None else list_input_devices()
    for key in ("m-audio m-track", "m-track solo and duo", "m-track duo", "m-track"):
        found = find_device_by_substring(key, devices)
        if found:
            return found
    return None


def resolve_device(
    config_device: Optional[int] = None,
    host_api: Optional[str] = None,
    preferred_substring: Optional[str] = None,
) -> int:
    """Pick a concrete input device index using this precedence:

    1. explicit config.device (if it is a valid input device)
    2. explicit preferred_substring match
    3. M-Track Duo auto-detect
    4. system default input
    5. first available input device
    """
    devices = list_input_devices()
    if host_api:
        devices = filter_by_host_api(devices, host_api)
    if not devices:
        raise RuntimeError("No input audio devices found")

    if config_device is not None:
        for d in devices:
            if d["index"] == config_device:
                return config_device
        raise ValueError(
            f"Device index {config_device} is not an available input device"
        )

    if preferred_substring:
        found = find_device_by_substring(preferred_substring, devices)
        if found:
            return found["index"]

    mtrack = find_mtrack_duo(devices)
    if mtrack:
        return mtrack["index"]

    default_in = sd.default.device[0]
    if default_in is not None and any(d["index"] == default_in for d in devices):
        return default_in

    return devices[0]["index"]
