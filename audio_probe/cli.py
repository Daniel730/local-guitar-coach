"""Command-line entry point for MVP-0.

Usage:
  python -m audio_probe               # probe 2s on auto-selected device
  python -m audio_probe --list        # list input devices
  python -m audio_probe --seconds 5   # capture 5 seconds
  python -m audio_probe --device 1     # force device index
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import AudioConfig
from .devices import list_input_devices
from .meters import to_dbfs
from .probe import AudioProbe


def _fmt_dbfs(x: float) -> str:
    return "-inf dBFS" if x == float("-inf") else f"{x:.1f} dBFS"


def cmd_list() -> int:
    devices = list_input_devices()
    print(f"{'idx':>3}  {'host':<22} {'ch':>2}  name")
    print("-" * 60)
    for d in devices:
        mark = "*" if d["is_default"] else " "
        print(
            f"{d['index']:>3}{mark} {d['host_api'][:22]:<22} "
            f"{d['max_input_channels']:>2}  {d['name']}"
        )
    return 0


def cmd_probe(args) -> int:
    config = AudioConfig(
        device=args.device,
        host_api=args.host_api,
        sample_rate=args.sample_rate,
        channels=args.channels,
    )
    probe = AudioProbe(config=config)
    print(f"Probing {args.seconds}s on device "
          f"{'auto' if args.device is None else args.device} ...")
    result = probe.run(seconds=args.seconds, on_meter=_print_meter)
    print()
    print("RESULT")
    print(f"  device       : {result.device_index} ({result.device_name})")
    print(f"  detected      : {result.detected}")
    print(f"  blocks        : {result.blocks_received}")
    print(f"  max peak      : {result.max_peak:.4f} ({_fmt_dbfs(to_dbfs(result.max_peak))})")
    lat = result.latency
    if lat["samples"] or lat["source"] == "configured":
        print(f"  input latency : mean {lat['mean']*1000:.1f} ms "
              f"(min {lat['min']*1000:.1f}, max {lat['max']*1000:.1f}) "
              f"[{lat['samples']} blocks, {lat['source']}]")
    else:
        print("  input latency : n/a")
    if args.json:
        print(json.dumps(result.__dict__, default=str, indent=2))
    return 0


def _print_meter(reading: dict) -> None:
    bar_len = 32
    level = reading["peak_hold"]
    filled = int(min(1.0, level) * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\r  [{bar}] peak {_fmt_dbfs(reading['peak_hold_dbfs'])} "
          f"rms {_fmt_dbfs(reading['rms_dbfs'])}", end="", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="audio_probe", description="Local Guitar Coach — MVP-0 Audio Probe"
    )
    parser.add_argument("--list", action="store_true", help="list input devices and exit")
    parser.add_argument("--seconds", type=float, default=2.0, help="capture duration")
    parser.add_argument("--device", type=int, default=None, help="force input device index")
    parser.add_argument("--host-api", default=None, help="e.g. MME, WASAPI")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--channels", type=int, default=1, choices=[1, 2])
    parser.add_argument("--json", action="store_true", help="emit JSON result")
    args = parser.parse_args(argv)

    if args.list:
        return cmd_list()
    return cmd_probe(args)


if __name__ == "__main__":
    sys.exit(main())
