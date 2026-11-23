"""Install the KWin script, bind chords and launch apps.

SUBSYSTEM: shortcuts
Reads: shortcuts.json, KWin, KGlobalAccel.
Writes: KWin package, kwinrc, KGlobalAccel, D-Bus interface, systemd scopes, log.
ADR: docs/adr/0008-shortcuts-and-kwin-script.md
"""

SUBSYSTEM = "shortcuts"


async def run(config: None, *, once: bool = False) -> None:
    """Serve the interface, then install the script; ``once`` stops there."""
    from functools import partial

    from dbus_fast import BusType
    from dbus_fast.aio import MessageBus

    from odsod_daemon.components.shortcuts import contract, kwin_install
    from odsod_daemon.components.shortcuts.kglobalaccel import DBusKGlobalAccel
    from odsod_daemon.components.shortcuts.service import Shortcuts

    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        shortcuts = contract.load().shortcuts
        bus.export(contract.OBJECT_PATH, Shortcuts(shortcuts, DBusKGlobalAccel(bus)))
        await bus.request_name(contract.BUS_NAME)
        await kwin_install.ensure(reload=partial(kwin_install.reconfigure, bus))
        if not once:
            await bus.wait_for_disconnect()
    finally:
        bus.disconnect()
