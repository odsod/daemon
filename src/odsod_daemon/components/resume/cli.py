"""Clear the pause and start capture only in a graphical session."""

from typing import Literal

import typer

from odsod_daemon.components.pause import flag
from odsod_daemon.components.pause.contract import ControlResult
from odsod_daemon.components.resume.contract import ResumeRecord
from odsod_daemon.lib import cli, clock, paths, streams, systemd

app = typer.Typer(add_completion=False)


def resume(by: Literal["cli", "tray", "timer", "login"] = "cli") -> ControlResult:
    roots = paths.roots()
    paused = flag.read(roots.run)
    if paused:
        flag.remove(roots.run)
        now = clock.utc_now()
        streams.append(
            streams.day_path(roots.state / "events/user", now.date()),
            ResumeRecord(ts=clock.iso(now), by=by).model_dump(),
        )
    if systemd.control("is-active", "graphical-session.target", check=False):
        systemd.control("start", "odsod-daemon-capture.service")
    return ControlResult(state="running", changed=paused is not None)


@app.callback(invoke_without_command=True)
def resume_command(
    as_json: bool = typer.Option(False, "--json"),
    by: Literal["cli", "tray", "timer", "login"] = typer.Option("cli", "--by"),
) -> None:
    """Resume recording in the graphical session."""
    try:
        cli.emit(
            resume(by),
            as_json=as_json,
            text=lambda r: "resumed" if r.changed else "already resumed",
        )
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
