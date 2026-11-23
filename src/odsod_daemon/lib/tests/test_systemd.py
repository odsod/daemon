from __future__ import annotations

import socket
from pathlib import Path

import pytest

from odsod_daemon.lib import systemd


def test_unit_object_path_escapes_names() -> None:
    assert (
        systemd.unit_object_path("odsod-daemon-capture.service")
        == "/org/freedesktop/systemd1/unit/odsod_2ddaemon_2dcapture_2eservice"
    )
    assert (
        systemd.unit_object_path("a@b.service")
        == "/org/freedesktop/systemd1/unit/a_40b_2eservice"
    )


def test_sd_notify_without_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert systemd.sd_notify("READY=1") is False


def test_sd_notify_sends_datagram(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "notify.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(1)
    monkeypatch.setenv("NOTIFY_SOCKET", str(path))
    try:
        assert systemd.sd_notify("READY=1") is True
        assert receiver.recv(64) == b"READY=1"
    finally:
        receiver.close()


def test_watchdog_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert systemd.watchdog_interval() is None
    monkeypatch.setenv("WATCHDOG_USEC", "200000")
    assert systemd.watchdog_interval() == pytest.approx(0.1)
    monkeypatch.setenv("WATCHDOG_USEC", "nope")
    assert systemd.watchdog_interval() is None


async def test_fake_unit_states() -> None:
    fake = systemd.FakeUnitStates()
    state = systemd.UnitState(
        unit="odsod-daemon-capture.service",
        scope="user",
        active_state="active",
        sub_state="running",
        result="success",
        state_change_timestamp=1,
    )
    fake.set(state)
    assert await fake.get(state.unit) == state
    assert await fake.get(state.unit, scope="system") is None
