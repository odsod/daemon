"""Take one snapshot and print the shared health evaluation."""

import asyncio

import typer

from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    StatusReport,
)
from odsod_daemon.components.health.evaluate import evaluate
from odsod_daemon.components.health.snapshot import gather
from odsod_daemon.components.status.render import render
from odsod_daemon.lib import cli, clock, config, paths, systemd

app = typer.Typer(add_completion=False)


async def report() -> StatusReport:
    roots = paths.roots()
    source = systemd.DBusUnitStates()
    try:
        async with clock.timeout(5):
            settings = config.section("control", ControlConfig, roots=roots)
            return evaluate(await gather(roots, source, settings=settings), settings)
    finally:
        await source.close()


@app.callback(invoke_without_command=True)
def status_command(as_json: bool = typer.Option(False, "--json")) -> None:
    """Report running state and return its Nagios exit code."""
    try:
        result = asyncio.run(report())
    except Exception as error:
        now = clock.iso()
        result = StatusReport(
            state="unknown",
            exit_code=3,
            ts=now,
            backlog=Backlog(count=0, seconds=0),
            mode="idle",
            dictation=DictationState(available=False, reason="session-down"),
            reasons=[
                Reason(
                    code="status-unreadable",
                    severity="error",
                    service="control",
                    since=now,
                    message=f"Cannot read daemon status: {error}",
                )
            ],
        )
    cli.emit(result, as_json=as_json, text=render)
    raise typer.Exit(result.exit_code)
