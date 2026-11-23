"""Read one local day's transcript as Markdown or JSON."""

from datetime import date

import typer
from pydantic import BaseModel, Field

from odsod_daemon.components.transcript.config import local_zone
from odsod_daemon.components.transcript.contract import Line, parse_file
from odsod_daemon.lib import cli, clock, config, paths, streams

app = typer.Typer(
    invoke_without_command=True, context_settings={"allow_interspersed_args": True}
)


class TranscriptResult(BaseModel):
    day: str
    host: str
    finished: bool
    lines: list[Line] = Field(default_factory=list)


@app.callback()
def transcript(
    day: str | None = typer.Option(None, "--day"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    if day is None:
        selected = clock.utc_now().astimezone(local_zone()).date()
    else:
        try:
            selected = date.fromisoformat(day)
        except ValueError as error:
            raise typer.BadParameter("use YYYY-MM-DD", param_hint="--day") from error
    roots = paths.roots()
    host = config.load_common().host
    name = f"{selected.isoformat()}-{host}.md"
    path = roots.state / "documents/transcripts" / name
    text = path.read_text() if path.exists() else ""
    if not as_json:
        typer.echo(text, nl=False)
        return
    finished = any(
        record["document"] == name
        for file in (roots.state / "finished/transcript").glob("*.jsonl")
        for record in streams.read_day(file)
    )
    result = TranscriptResult(
        day=selected.isoformat(), host=host, finished=finished, lines=parse_file(text)
    )
    cli.emit(result, as_json=True, text=lambda _: text)
