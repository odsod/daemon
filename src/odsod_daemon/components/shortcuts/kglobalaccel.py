"""Configure: bind the listed keys in KGlobalAccel.

Remove stale ``[odsod]`` actions and clear conflicting bindings first.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

from odsod_daemon.components.shortcuts import keys
from odsod_daemon.components.shortcuts.contract import Shortcut

LOG = logging.getLogger(__name__)

COMPONENT = "kwin"
OWN_PREFIXES = ("[odsod]", "odsod")


class KGlobalAccel(Protocol):
    async def shortcut_names(self) -> list[str]: ...
    async def action(self, code: int) -> list[str]: ...
    async def set_foreign_shortcut(
        self, action_id: Sequence[str], codes: Sequence[int]
    ) -> None: ...
    async def unregister(self, component: str, name: str) -> None: ...


@dataclass
class Summary:
    bound: int = 0
    removed: int = 0
    conflicts: int = 0
    failed: int = 0


def stale_names(current: Iterable[str], listed: Iterable[str]) -> list[str]:
    """Own action names that KGlobalAccel has and the list lacks."""
    keep = set(listed)
    return [
        name for name in current if name.startswith(OWN_PREFIXES) and name not in keep
    ]


async def configure(client: KGlobalAccel, shortcuts: Sequence[Shortcut]) -> Summary:
    """Remove stale actions, clear conflicts, bind each listed key.

    A failed call is logged and skipped; the rest go on.
    """
    summary = Summary()
    try:
        current = await client.shortcut_names()
    except Exception as error:
        LOG.warning("configure: list actions failed: %s", error)
        current = []
        summary.failed += 1
    for name in stale_names(current, (shortcut.name for shortcut in shortcuts)):
        try:
            await client.unregister(COMPONENT, name)
            summary.removed += 1
        except Exception as error:
            LOG.warning("configure: unregister %s failed: %s", name, error)
            summary.failed += 1
    for shortcut in shortcuts:
        try:
            code = keys.parse(shortcut.key)
            other = await client.action(code)
            if other and list(other) != list(shortcut.action_id):
                await client.set_foreign_shortcut(other, [])
                summary.conflicts += 1
            await client.set_foreign_shortcut(shortcut.action_id, [code])
            summary.bound += 1
        except Exception as error:
            LOG.warning("configure: bind %s failed: %s", shortcut.name, error)
            summary.failed += 1
    LOG.info(
        "configure: bound %d, removed %d, conflicts cleared %d, failed %d",
        summary.bound,
        summary.removed,
        summary.conflicts,
        summary.failed,
    )
    return summary


@dataclass
class FakeKGlobalAccel:
    """An in-process KGlobalAccel for tests. It keeps bindings by action."""

    bindings: dict[tuple[str, ...], list[int]] = field(default_factory=dict)
    fail_on: set[str] = field(default_factory=set)
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    async def shortcut_names(self) -> list[str]:
        self.calls.append(("shortcutNames",))
        return [action[1] for action in self.bindings if action[0] == COMPONENT]

    async def action(self, code: int) -> list[str]:
        self.calls.append(("action", code))
        for action, codes in self.bindings.items():
            if code in codes:
                return list(action)
        return []

    async def set_foreign_shortcut(
        self, action_id: Sequence[str], codes: Sequence[int]
    ) -> None:
        self.calls.append(("setForeignShortcut", list(action_id), list(codes)))
        if action_id[1] in self.fail_on:
            raise RuntimeError(f"org.kde.kglobalaccel.NoSuchAction: {action_id[1]}")
        self.bindings[tuple(action_id)] = list(codes)

    async def unregister(self, component: str, name: str) -> None:
        self.calls.append(("unregister", component, name))
        for action in [a for a in self.bindings if a[:2] == (component, name)]:
            del self.bindings[action]


class DBusKGlobalAccel:
    """KGlobalAccel over the session bus (``org.kde.kglobalaccel``)."""

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def _call(
        self, path: str, interface: str, member: str, signature: str, body: list[Any]
    ) -> list[Any]:
        reply = await self._bus.call(
            Message(
                destination="org.kde.kglobalaccel",
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body,
            )
        )
        if reply is None:
            return []
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body}")
        return reply.body

    async def shortcut_names(self) -> list[str]:
        body = await self._call(
            f"/component/{COMPONENT}",
            "org.kde.kglobalaccel.Component",
            "shortcutNames",
            "",
            [],
        )
        return [str(name) for name in body[0]]

    async def action(self, code: int) -> list[str]:
        body = await self._call(
            "/kglobalaccel", "org.kde.KGlobalAccel", "action", "i", [code]
        )
        return [str(part) for part in body[0]]

    async def set_foreign_shortcut(
        self, action_id: Sequence[str], codes: Sequence[int]
    ) -> None:
        await self._call(
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            "setForeignShortcut",
            "asai",
            [list(action_id), list(codes)],
        )

    async def unregister(self, component: str, name: str) -> None:
        await self._call(
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            "unregister",
            "ss",
            [component, name],
        )
