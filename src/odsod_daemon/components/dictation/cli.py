"""Read the newest dictation without starting the session loop."""

import json

import typer

from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.components.dictation.last import newest
from odsod_daemon.lib import config

app = typer.Typer(add_completion=False)


@app.command("last")
def last(as_json: bool = typer.Option(False, "--json")) -> None:
    """Print the latest text, press time and raw or late marks."""
    result = newest(config.section("dictation", DictationConfig).text_timeout_s)
    if as_json:
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        marks = [mark for mark in ("raw", "late") if result.get(mark)]
        typer.echo(" ".join([result.get("press", ""), result["state"], *marks]).strip())
        if result["text"]:
            typer.echo(result["text"])
