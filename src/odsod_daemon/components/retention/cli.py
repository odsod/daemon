"""``odsodctl retention``: delete audio older than ``common.retention_days``."""

from __future__ import annotations

import typer
from pydantic import ValidationError

from odsod_daemon.components.retention import retention
from odsod_daemon.lib import clock, config, paths

app = typer.Typer(add_completion=False, help="Delete audio older than the period.")


@app.callback(invoke_without_command=True)
def retention_command() -> None:
    """Delete each audio hour file older than the retention period."""
    roots = paths.roots()
    try:
        common = config.load_common(roots)
    except (config.ConfigError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    now = clock.utc_now()
    failed = 0
    # ADR-0024: each satellite host root keeps the same period.
    states = [roots.state] + [roots.state / paths.HOSTS / h for h in paths.satellites()]
    for path in (p for state in states for p in retention.audio_files(state)):
        if not retention.is_expired(path, now, common.retention_days):
            continue
        try:
            path.unlink()
        except OSError as error:
            typer.echo(f"{path}: {error}", err=True)
            failed += 1
    if failed:
        raise typer.Exit(1)
