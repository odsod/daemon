"""Append an owner note without requiring a running pipeline."""

import sys

import typer

from odsod_daemon.components.note.contract import Note
from odsod_daemon.components.transcript.config import local_zone
from odsod_daemon.components.transcript.lines import from_record
from odsod_daemon.lib import cli, clock, paths, streams

app = typer.Typer(
    invoke_without_command=True, context_settings={"allow_interspersed_args": True}
)


@app.callback()
def note(
    text: str = typer.Argument(...), as_json: bool = typer.Option(False, "--json")
) -> None:
    record = Note(ts=clock.iso(), text=sys.stdin.read() if text == "-" else text)
    streams.append(
        streams.day_path(
            paths.roots().state / "events/user", clock.parse_iso(record.ts).date()
        ),
        record.model_dump(mode="json"),
    )

    def render(value: Note) -> str:
        line = from_record(value.model_dump(), local_zone())
        assert line is not None
        return line.render()

    cli.emit(record, as_json=as_json, text=render)
