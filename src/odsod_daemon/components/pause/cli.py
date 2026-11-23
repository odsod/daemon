"""Set recording intent before stopping capture."""

from typing import Literal

import typer

from odsod_daemon.components.pause import flag
from odsod_daemon.components.pause.contract import ControlResult, PauseRecord
from odsod_daemon.lib import cli, clock, paths, streams, systemd

app = typer.Typer(add_completion=False)


def pause(by: Literal["cli", "tray", "login"] = "cli") -> ControlResult:
    roots = paths.roots()
    paused = flag.read(roots.run)
    if paused:
        return ControlResult(state="paused", paused_since=paused.since, changed=False)
    now = clock.utc_now()
    since = clock.iso(now)
    flag.write(roots.run, since)
    streams.append(
        streams.day_path(roots.state / "events/user", now.date()),
        PauseRecord(ts=since, by=by).model_dump(),
    )
    systemd.control("stop", "odsod-daemon-capture.service")
    return ControlResult(state="paused", paused_since=since, changed=True)


def render(result: ControlResult) -> str:
    prefix = "" if result.changed else "already "
    return f"{prefix}paused since {result.paused_since}"


@app.callback(invoke_without_command=True)
def pause_command(
    as_json: bool = typer.Option(False, "--json"),
    by: Literal["cli", "tray", "login"] = typer.Option("cli", "--by"),
) -> None:
    """Pause capture until resume, next login or local midnight."""
    try:
        cli.emit(pause(by), as_json=as_json, text=render)
    except (OSError, ValueError, RuntimeError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
