"""`odsodctl audio`: play or export one utterance by its ID."""

from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from odsod_daemon.components.audio.contract import Clip
from odsod_daemon.lib import audio, paths, streams

app = typer.Typer(
    add_completion=False, help="Play or export the audio of an utterance."
)
ID = typer.Argument(..., metavar="ID", help="Utterance ID, as in <!-- id:… -->.")
OUTPUT = typer.Option(..., "-o", "--output", help="WAV file to write.")
PAD = typer.Option(1.0, "--pad", min=0, max=60, help="Seconds of context per side.")


def find(state: Path, ident: str) -> Clip:
    """Look up the utterance record: the ID gives the start, not the end."""
    channel, _, stamp = ident.partition("-")
    try:
        start = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError(f"not an utterance ID: {ident}") from error
    kind = "dictation" if channel == "dic" else "ambient"
    day = start.date()
    records = streams.read_days(
        state / "utterances" / kind, day, day + timedelta(days=1)
    )
    for record in records:
        if record.get("kind") == "utterance" and record.get("id") == ident:
            return Clip.model_validate(record)
    raise ValueError(f"no utterance with ID {ident}")


def wav(state: Path, clip: Clip, pad: float) -> bytes:
    margin = timedelta(seconds=pad)
    pcm = audio.cut(state, clip.channel, clip.start - margin, clip.end + margin)
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(audio.SAMPLE_RATE)
        handle.writeframes(pcm)
    return output.getvalue()


def _clip(ident: str, pad: float) -> bytes:
    state = paths.roots().state
    try:
        return wav(state, find(state, ident), pad)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@app.command("export")
def export_command(
    ident: str = ID,
    output: Path = OUTPUT,
    pad: float = PAD,
) -> None:
    """Write the utterance as a 16 kHz mono WAV file."""
    output.write_bytes(_clip(ident, pad))
    typer.echo(str(output))


@app.command("play")
def play_command(ident: str = ID, pad: float = PAD) -> None:
    """Play the utterance on the default output with pw-play."""
    data = _clip(ident, pad)
    with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
        handle.write(data)
        handle.flush()
        code = subprocess.run(["pw-play", handle.name], check=False).returncode
    raise typer.Exit(code)
