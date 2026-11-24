"""Crash cleanup without the session loop or speech modules."""

import asyncio

import typer

from odsod_daemon.components.dictation import pactl
from odsod_daemon.components.dictation.contract import MutedDocument
from odsod_daemon.components.dictation.pactl import unmute
from odsod_daemon.lib import documents, paths

app = typer.Typer(add_completion=False)


async def cleanup() -> None:
    path = paths.roots().run / "muted.json"
    if path.exists():
        record = MutedDocument.model_validate(documents.read_json(path))
        try:
            await unmute([(s.id, s.app) for s in record.streams])
        finally:
            # A hold that lifted a mic mute: mute the mic again.
            if record.source:
                await pactl.set_source_mute(record.source, True)


@app.callback(invoke_without_command=True)
def unmute_stale() -> None:
    """Unmute recorded streams and mute a recorded mic, without changing the record."""
    try:
        asyncio.run(cleanup())
    except (OSError, TimeoutError, ValueError) as error:
        typer.echo(f"unmute-stale: {error}", err=True)
        raise typer.Exit(1) from error
