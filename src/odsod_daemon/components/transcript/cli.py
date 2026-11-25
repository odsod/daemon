"""Read one local day's transcript as Markdown or JSON."""

import subprocess
import sys
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
    host: str | None = typer.Option(None, "--host", help="A satellite's host root"),
) -> None:
    common = config.load_common()
    if host is None and common.role == "satellite":
        # ADR-0024: the base makes this host's transcript.
        assert common.base is not None
        command = ["odsodctl", "transcript", "--host", common.host]
        command += ["--day", day] if day else []
        command += ["--json"] if as_json else []
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", common.base, "--", *command], check=False
        )
        sys.exit(result.returncode)
    if host is not None and host != common.host:
        with paths.host(host):
            _show(day, as_json)
        return
    _show(day, as_json)


def _show(day: str | None, as_json: bool) -> None:
    if day is None:
        selected = clock.utc_now().astimezone(local_zone()).date()
    else:
        try:
            selected = date.fromisoformat(day)
        except ValueError as error:
            raise typer.BadParameter("use YYYY-MM-DD", param_hint="--day") from error
    roots = paths.roots()
    host = config.host_name()
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
