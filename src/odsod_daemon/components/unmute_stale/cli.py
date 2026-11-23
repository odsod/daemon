"""Crash cleanup without the session loop or speech modules."""

import asyncio

import typer

from odsod_daemon.components.dictation.contract import MutedDocument
from odsod_daemon.components.dictation.pactl import unmute
from odsod_daemon.lib import documents, paths

app = typer.Typer(add_completion=False)


async def cleanup() -> None:
    path = paths.roots().run / "muted.json"
    if path.exists():
        record = MutedDocument.model_validate(documents.read_json(path))
        await unmute([(s.id, s.app) for s in record.streams])


@app.callback(invoke_without_command=True)
def unmute_stale() -> None:
    """Unmute recorded streams without changing the record."""
    try:
        asyncio.run(cleanup())
    except (OSError, TimeoutError, ValueError) as error:
        typer.echo(f"unmute-stale: {error}", err=True)
        raise typer.Exit(1) from error
