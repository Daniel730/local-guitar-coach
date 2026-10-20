"""CHANGE-03 regression tests: P1-A (no hardcoded device/channel) + P1-B (persistence).

Rules: only frontend + app/services were touched; perception/, audio_probe/stream.py
are untouched by this change. These tests prove the contracts enforced by CHANGE-03.
"""
from __future__ import annotations
import json
import re
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
APP_JS = REPO / "frontend" / "app.js"


# ---- P1-A: no hardcoded device/channel in the Web App start_session ----

def _start_session_block() -> str:
    """Extract the startSession() object literal from frontend/app.js."""
    text = APP_JS.read_text(encoding="utf-8")
    m = re.search(r"type:\s*\"start_session\"(.*?)\}\);", text, re.S)
    assert m, "start_session block not found in app.js"
    return m.group(1)


def test_p1a_no_hardcoded_device_in_start_session():
    """device must NOT be the literal 1 (must come from /api/devices)."""
    block = _start_session_block()
    # 'device:' must reference the selectedDevice variable, not a literal integer.
    assert re.search(r"device:\s*selectedDevice", block), \
        "start_session must send device from /api/devices (selectedDevice), got literal"
    assert not re.search(r"device:\s*1\b", block), \
        "hardcoded device: 1 still present"


def test_p1a_no_hardcoded_channel_in_start_session():
    """channel must reference selectedChannel (derived from device), not a blind literal 1."""
    block = _start_session_block()
    assert re.search(r"channel:\s*selectedChannel", block), \
        "start_session must send channel via selectedChannel, got literal"
    assert not re.search(r"channel:\s*1\b", block), \
        "hardcoded channel: 1 still present"


def test_p1a_channel_derived_from_device_channels():
    """selectedChannel must be derived from the device's channel count, not a fixed 1."""
    text = APP_JS.read_text(encoding="utf-8")
    # The derivation rule must exist: stereo -> CH2 (1), mono -> CH1 (0).
    assert re.search(r"selectedChannel\s*=\s*selectedDeviceChannels\s*>=\s*2\s*\?\s*1\s*:\s*0", text), \
        "selectedChannel must be derived from selectedDeviceChannels (>=2 ? 1 : 0)"
    assert "selectedDeviceChannels" in text, "device channel count not captured"


def test_p1a_loadDevices_present():
    """The frontend must query /api/devices (the source of truth)."""
    text = APP_JS.read_text(encoding="utf-8")
    assert "/api/devices" in text, "app.js no longer fetches /api/devices"
    assert "loadDevices" in text, "loadDevices() not defined"


# ---- P1-B: session persistence writes performance + skill state ----

def test_p1b_persist_performance_and_skill(tmp_path, monkeypatch):
    """persist_session writes a per-session performance JSON + a skill_<skill>.json."""
    from types import SimpleNamespace

    from perception.performance import PerformanceResult
    from perception.skill import SkillState

    # Point persistence's data dir at a temp dir so we don't pollute data/sessions.
    monkeypatch.setattr("perception.persistence._session_dir",
                        lambda: (tmp_path / "sessions"))
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)

    from app.services.session_service import SessionService
    svc = SessionService()

    # Build a fake teacher_service with a coherent PerformanceResult.
    perf = PerformanceResult(
        exercise_id="scale_e_minor_001",
        note_accuracy=0.5,
        timing_accuracy=0.3,
        uncertain_ratio=0.0,
        target_bpm=100.0,
        performed_bpm=90.0,
        tempo_ratio=0.9,
        mean_timing_error_ms=120.0,
    )
    fake = SimpleNamespace(
        exercise=SimpleNamespace(skill="pentatonic"),
        _performance=perf,
    )

    sid = "test_sess"
    session = SimpleNamespace(
        exercise_id="scale_e_minor_001",
        target_bpm=100.0,
        status="running",
    )
    svc._sessions[sid] = session
    svc._teacher_services[sid] = fake

    svc.persist_session(sid)

    # Per-session performance file
    perf_files = list((tmp_path / "sessions").glob("test_sess.json"))
    assert perf_files, "no per-session performance file written for test_sess"
    data = json.loads(perf_files[0].read_text(encoding="utf-8"))
    assert data["exercise_id"] == "scale_e_minor_001"
    assert data["note_accuracy"] == 0.5

    # Skill state file
    skill_files = list((tmp_path / "sessions").glob("skill_pentatonic.json"))
    assert skill_files, "no skill_pentatonic.json written"
    skill = json.loads(skill_files[0].read_text(encoding="utf-8"))
    assert skill["skill"] == "pentatonic"
    assert skill["attempts"], "skill state should record the attempt"
    assert skill["attempts"][0]["exercise_id"] == "scale_e_minor_001"


def test_p1b_no_perf_is_noop(tmp_path, monkeypatch):
    """persist_session with no performance must not crash nor write files."""
    from types import SimpleNamespace

    monkeypatch.setattr("perception.persistence._session_dir",
                        lambda: (tmp_path / "sessions"))
    (tmp_path / "sessions").mkdir(parents=True, exist_ok=True)

    from app.services.session_service import SessionService
    svc = SessionService()
    sid = "nosess"
    svc._sessions[sid] = SimpleNamespace(exercise_id="x", target_bpm=100.0, status="running")
    svc._teacher_services[sid] = SimpleNamespace(exercise=SimpleNamespace(skill="s"), _performance=None)

    svc.persist_session(sid)  # must not raise

    assert list((tmp_path / "sessions").glob("*.json")) == [], \
        "nothing should be written when there is no performance result"