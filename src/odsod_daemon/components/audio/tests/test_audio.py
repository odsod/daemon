import wave
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.lib import audio, streams

START = datetime(2026, 11, 24, 10, 2, 14, 108000, tzinfo=UTC)
ID = "sys-20261124T100214.108Z"


def setup(root: Path) -> None:
    state = root / "state"
    hour = audio.hour_file(state, "sys", START)
    hour.parent.mkdir(parents=True, exist_ok=True)
    hour.write_bytes(b"\x01\x00" * audio.SAMPLE_RATE * 3600)
    streams.append(
        streams.day_path(state / "utterances" / "ambient", START.date()),
        {
            "kind": "utterance",
            "id": ID,
            "channel": "sys",
            "start": "2026-11-24T10:02:14.108Z",
            "end": "2026-11-24T10:02:16.108Z",
        },
    )


def test_export_writes_the_utterance_with_padding(tmp_path, monkeypatch):
    """PRD ambient-recording AC-21: an utterance ID gives its audio."""
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    setup(tmp_path)
    out = tmp_path / "clip.wav"
    result = CliRunner().invoke(
        app, ["audio", "export", ID, "-o", str(out), "--pad", "1"]
    )
    assert result.exit_code == 0, result.output
    with wave.open(str(out)) as handle:
        assert handle.getframerate() == 16000
        assert handle.getnframes() == 4 * 16000


def test_unknown_id_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    setup(tmp_path)
    for ident in ["sys-20261124T100215.000Z", "nonsense"]:
        result = CliRunner().invoke(app, ["audio", "export", ident, "-o", "x.wav"])
        assert result.exit_code == 1
