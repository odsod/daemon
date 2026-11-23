"""Table tests for the pure checks (ADR-0011 "Mic checks")."""

from __future__ import annotations

from odsod_daemon.components.capture import checks

ZERO = bytes(3_200)
LOUD = (7).to_bytes(2, "little") * 1_600


def test_all_zero() -> None:
    assert checks.all_zero(ZERO)
    assert not checks.all_zero(LOUD)
    assert not checks.all_zero(bytes(99) + b"\x01\x00" + bytes(99))


def test_zero_run_faults_at_the_threshold_and_clears() -> None:
    mic = checks.MicCheck(silent_s=60)
    for index in range(600):
        mic.block(ZERO, start=index * 0.1)
    assert mic.faults(now=59.9) == []
    active = mic.faults(now=60.0)
    assert active == [checks.Active(checks.MIC_SILENT, since=0.0)]
    mic.block(LOUD, start=60.0)
    assert mic.faults(now=61.0) == []


def test_zero_run_restarts_after_one_loud_block() -> None:
    mic = checks.MicCheck(silent_s=10)
    mic.block(ZERO, start=0.0)
    mic.block(LOUD, start=0.1)
    mic.block(ZERO, start=5.0)
    assert mic.faults(now=14.9) == []
    assert mic.faults(now=15.0) == [checks.Active(checks.MIC_SILENT, since=5.0)]


def test_muted_source_shows_mic_muted_and_no_silent_fault() -> None:
    mic = checks.MicCheck(silent_s=10)
    mic.set_muted(True, now=1.0)
    for index in range(200):
        mic.block(ZERO, start=index * 0.1)
    assert mic.faults(now=30.0) == [checks.Active(checks.MIC_MUTED, since=1.0)]
    mic.set_muted(False, now=31.0)
    assert mic.zero_since is None
    assert mic.faults(now=31.0) == []
    mic.block(ZERO, start=31.0)
    mic.set_muted(False, now=35.0)
    assert mic.faults(now=40.9) == []
    assert mic.faults(now=41.0) == [checks.Active(checks.MIC_SILENT, since=31.0)]


def test_stall_start_is_the_later_of_audio_end_and_service_start() -> None:
    assert checks.stall_start(None, 10.0, floor=10.0) == 10.0
    assert checks.stall_start(5.0, 10.0, floor=10.0) == 10.0
    assert checks.stall_start(20.0, 10.0, floor=10.0) == 20.0
    assert not checks.is_stalled(10.0, 69.9, 60.0)
    assert checks.is_stalled(10.0, 70.0, 60.0)


def test_watchdog_needs_both_channels_inside_the_window() -> None:
    assert checks.watchdog_ok({"mic": 100.0, "sys": 99.0}, now=100.0)
    assert not checks.watchdog_ok({"mic": 100.0, "sys": 94.9}, now=100.0)
    assert not checks.watchdog_ok({"mic": 100.0}, now=100.0)


def test_mic_fault_since_keeps_the_first_zero_block() -> None:
    mic = checks.MicCheck(silent_s=1)
    mic.block(ZERO, start=2.0)
    mic.block(ZERO, start=2.1)
    assert mic.faults(now=3.0) == [checks.Active(checks.MIC_SILENT, since=2.0)]


def test_unmute_discards_zeros_from_before_and_during_mute() -> None:
    mic = checks.MicCheck(silent_s=60)
    mic.block(ZERO, start=0)
    mic.set_muted(True, now=10)
    mic.block(ZERO, start=70)
    mic.set_muted(False, now=80)
    assert mic.faults(now=80) == []
    mic.block(ZERO, start=81)
    assert mic.faults(now=140.9) == []
    assert mic.faults(now=141) == [checks.Active(checks.MIC_SILENT, since=81)]


def test_stall_floor_resets_only_after_a_clean_exit() -> None:
    """ADR-0011: a stall that began before a watchdog restart still shows."""
    assert checks.stall_floor(None, None, 1000.0) == 1000.0
    assert checks.stall_floor("stop", 990.0, 1000.0) == 1000.0
    # Crash or watchdog kill: no stop, and audio was recent.
    assert checks.stall_floor("start", 990.0, 1000.0) is None
    assert checks.stall_floor("gap", 900.0, 1000.0) is None
    # Old crash (power loss last night): a new day starts clean.
    assert checks.stall_floor("start", 500.0, 1000.0) == 1000.0


def test_stall_start_keeps_a_stall_across_restarts() -> None:
    assert checks.stall_start(5.0, 10.0, floor=None) == 5.0
    assert checks.stall_start(None, 10.0, floor=None) == 10.0
