"""Pause and resume sync to the base, such as on mobile data."""

from __future__ import annotations

from collections.abc import Callable

import typer

from odsod_daemon.components.sync import flag
from odsod_daemon.components.sync.contract import SyncResult
from odsod_daemon.lib import cli, clock, config, paths

app = typer.Typer(no_args_is_help=True, add_completion=False)


def satellite() -> paths.Roots:
    if config.load_common().role != "satellite":
        raise ValueError("this host is not a satellite; it has no sync")
    return paths.roots()


def pause() -> SyncResult:
    roots = satellite()
    paused = flag.read(roots.state)
    if paused:
        return SyncResult(state="paused", paused_since=paused.since, changed=False)
    since = clock.iso()
    flag.write(roots.state, since)
    return SyncResult(state="paused", paused_since=since, changed=True)


def resume() -> SyncResult:
    roots = satellite()
    paused = flag.read(roots.state)
    if paused:
        flag.remove(roots.state)
    return SyncResult(state="running", changed=paused is not None)


def render(result: SyncResult) -> str:
    prefix = "" if result.changed else "already "
    if result.state == "paused":
        return f"sync {prefix}paused since {result.paused_since}"
    return f"sync {prefix}running"


def emit(action: Callable[[], SyncResult], as_json: bool) -> None:
    try:
        cli.emit(action(), as_json=as_json, text=render)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@app.command("pause")
def pause_command(as_json: bool = typer.Option(False, "--json")) -> None:
    """Stop sending audio to the base. Capture keeps recording here."""
    emit(pause, as_json)


@app.command("resume")
def resume_command(as_json: bool = typer.Option(False, "--json")) -> None:
    """Send audio to the base again. Sync catches up from where it stopped."""
    emit(resume, as_json)
