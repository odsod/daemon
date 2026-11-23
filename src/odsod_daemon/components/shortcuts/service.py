"""The D-Bus interface that the KWin script calls.

``Configure`` and ``Run`` use the service's own copy of the list. ``Run``
refuses a name that is not in it, so no caller on the session bus can make
the service run an arbitrary command.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from dbus_fast import DBusError
from dbus_fast.annotations import DBusStr
from dbus_fast.service import ServiceInterface, dbus_method

from odsod_daemon.components.shortcuts import kglobalaccel, launcher
from odsod_daemon.components.shortcuts.contract import INTERFACE, Shortcut

LOG = logging.getLogger(__name__)

UNKNOWN = f"{INTERFACE}.Error.UnknownShortcut"

Launch = Callable[[Shortcut], Coroutine[Any, Any, None]]


class Shortcuts(ServiceInterface):
    def __init__(
        self,
        shortcuts: Sequence[Shortcut],
        accel: kglobalaccel.KGlobalAccel,
        launch: Launch = launcher.launch,
    ) -> None:
        super().__init__(INTERFACE)
        self._shortcuts = list(shortcuts)
        self._by_name = {s.name: s for s in shortcuts if s.kind in ("app", "command")}
        self._accel = accel
        self._launch = launch
        self._tasks: set[asyncio.Task[None]] = set()

    @dbus_method()
    async def Configure(self):
        await kglobalaccel.configure(self._accel, self._shortcuts)

    @dbus_method()
    def Run(self, name: DBusStr):
        shortcut = self._by_name.get(name)
        if shortcut is None:
            LOG.warning("run %r: not in the list, refused", name)
            raise DBusError(UNKNOWN, f"no shortcut named {name!r}")
        task = asyncio.get_running_loop().create_task(self._launch(shortcut))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @dbus_method()
    def Log(self, values: DBusStr):
        try:
            parts = json.loads(values)
        except ValueError:
            parts = [values]
        if not isinstance(parts, list):
            parts = [parts]
        LOG.info("script: %s", " ".join(str(part) for part in parts))
