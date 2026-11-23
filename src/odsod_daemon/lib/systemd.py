"""systemd unit states over D-Bus, and ``sd_notify``.

The fake unit-state source is for tests. It never talks to a real systemd.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from dbus_fast import BusType
from dbus_fast.aio import MessageBus


@dataclass(frozen=True)
class UnitState:
    unit: str
    scope: str
    active_state: str
    sub_state: str
    result: str
    state_change_timestamp: int


class UnitStateSource(Protocol):
    async def get(self, unit: str, *, scope: str = "user") -> UnitState | None: ...


@dataclass
class FakeUnitStates:
    """A fake source for tests."""

    units: dict[tuple[str, str], UnitState] = field(default_factory=dict)

    def set(self, state: UnitState) -> None:
        self.units[(state.scope, state.unit)] = state

    async def get(self, unit: str, *, scope: str = "user") -> UnitState | None:
        return self.units.get((scope, unit))


def unit_object_path(unit: str) -> str:
    escaped = "".join(char if char.isalnum() else f"_{ord(char):02x}" for char in unit)
    return "/org/freedesktop/systemd1/unit/" + escaped


class DBusUnitStates:
    """Read unit properties from the user or system bus."""

    def __init__(self) -> None:
        self._buses: dict[str, MessageBus] = {}

    async def _bus(self, scope: str) -> MessageBus:
        if scope not in self._buses:
            bus_type = BusType.SYSTEM if scope == "system" else BusType.SESSION
            self._buses[scope] = await MessageBus(bus_type=bus_type).connect()
        return self._buses[scope]

    async def get(self, unit: str, *, scope: str = "user") -> UnitState | None:
        bus = await self._bus(scope)
        try:
            introspection = await bus.introspect(
                "org.freedesktop.systemd1", unit_object_path(unit)
            )
            proxy = bus.get_proxy_object(
                "org.freedesktop.systemd1", unit_object_path(unit), introspection
            )
            properties = cast(
                Any, proxy.get_interface("org.freedesktop.DBus.Properties")
            )
            values = {}
            for name in (
                "ActiveState",
                "SubState",
                "Result",
                "StateChangeTimestamp",
            ):
                variant = await properties.call_get(
                    "org.freedesktop.systemd1.Unit", name
                )
                values[name] = variant.value
        except Exception as error:
            if "NoSuchUnit" in str(error):
                return None
            raise
        return UnitState(
            unit=unit,
            scope=scope,
            active_state=str(values["ActiveState"]),
            sub_state=str(values["SubState"]),
            result=str(values["Result"]),
            state_change_timestamp=int(values["StateChangeTimestamp"]),
        )

    async def close(self) -> None:
        for bus in self._buses.values():
            bus.disconnect()
        self._buses.clear()


def sd_notify(state: str, *, unset_environment: bool = False) -> bool:
    """Send a datagram to ``$NOTIFY_SOCKET``. False when it is not set."""
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(state.encode("utf-8"), address)
        except OSError:
            return False
    if unset_environment:
        os.environ.pop("NOTIFY_SOCKET", None)
    return True


def watchdog_interval() -> float | None:
    """Half of ``WATCHDOG_USEC`` in seconds, or None when it is not set."""
    raw = os.environ.get("WATCHDOG_USEC")
    if not raw:
        return None
    try:
        usec = int(raw)
    except ValueError:
        return None
    if usec <= 0:
        return None
    return usec / 1_000_000 / 2
