"""Notify once when systemd gives up on a unit."""

import re

import typer

from odsod_daemon.components.notify_failed.contract import Notification
from odsod_daemon.components.notify_failed.notify import send

app = typer.Typer(add_completion=False)


@app.callback(invoke_without_command=True)
def notify_failed_command(unit: str = typer.Argument(...)) -> None:
    """Send the unit name and the command that restarts it."""
    if not re.fullmatch(r"odsod-daemon-[a-z0-9@_.:-]+", unit):
        raise typer.BadParameter("expected an odsod-daemon unit")
    service = unit.removeprefix("odsod-daemon-").removesuffix(".service")
    prefix = "sudo systemctl" if service == "keys" else "systemctl --user"
    notification = Notification(
        title=f"odsod-daemon: {service} failed",
        body=f"{prefix} restart {unit}. Details: odsodctl status.",
        urgency="critical",
    )
    if not send(notification):
        typer.echo(f"notify-send failed for {unit}", err=True)
