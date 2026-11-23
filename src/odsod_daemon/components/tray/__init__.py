"""Show the state and the Pause or Resume menu.

SUBSYSTEM: control
Reads: The health evaluation, run/status.json.
Writes: Desktop notifications, command starts.
ADR: docs/adr/0018-control.md
"""

from __future__ import annotations

from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.tray.worker import TrayWorker
from odsod_daemon.lib import paths, systemd

SUBSYSTEM = "control"

CONFIG_MODEL = ControlConfig


async def run(settings: ControlConfig, *, once: bool = False) -> None:
    roots = paths.roots()
    source = systemd.DBusUnitStates()
    if once:
        try:
            await TrayWorker(
                roots, source, settings, report=lambda _report: None
            ).evaluate_once()
        finally:
            await source.close()
        return
    from odsod_daemon.components.tray.app import run as run_app

    try:
        run_app(roots, source, settings)
    finally:
        await source.close()
