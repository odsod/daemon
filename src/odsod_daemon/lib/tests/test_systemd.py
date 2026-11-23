from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from odsod_daemon.lib import systemd

UNIT = "org.freedesktop.systemd1.Unit"
SERVICE = "org.freedesktop.systemd1.Service"
TIMER = "org.freedesktop.systemd1.Timer"


class FakeProperties:
    def __init__(self, values: dict[tuple[str, str], object]) -> None:
        self.values = values
        self.calls: list[tuple[str, str]] = []

    async def call_get(self, interface: str, name: str) -> object:
        self.calls.append((interface, name))
        try:
            value = self.values[(interface, name)]
        except KeyError:
            raise AssertionError(f"no property {interface}.{name}") from None
        return SimpleNamespace(value=value)


UNIT_VALUES = {
    (UNIT, "ActiveState"): "failed",
    (UNIT, "SubState"): "failed",
    (UNIT, "StateChangeTimestamp"): 42,
}


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


def test_result_interface_by_unit_type() -> None:
    assert systemd.result_interface("a.service") == SERVICE
    assert systemd.result_interface("a.timer") == TIMER
    assert systemd.result_interface("a.socket") is None


async def test_read_state_reads_result_from_the_unit_type_interface() -> None:
    properties = FakeProperties({**UNIT_VALUES, (SERVICE, "Result"): "exit-code"})
    state = await systemd.read_state("capture.service", "user", properties)
    assert state.active_state == "failed"
    assert state.result == "exit-code"
    assert state.state_change_timestamp == 42
    assert (SERVICE, "Result") in properties.calls
    result_interfaces = {
        interface for interface, name in properties.calls if name == "Result"
    }
    assert result_interfaces == {SERVICE}


async def test_read_state_defaults_result_when_the_unit_type_has_none() -> None:
    properties = FakeProperties(UNIT_VALUES)
    state = await systemd.read_state("capture.socket", "user", properties)
    assert state.result == ""
    assert {interface for interface, _name in properties.calls} == {UNIT}
