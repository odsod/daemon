import json

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.components.transcript.tests.conftest import append
from odsod_daemon.components.transcript.tests.test_core import RECORDS, ZONE
from odsod_daemon.components.transcript.writer import Writer
from odsod_daemon.lib import clock


def test_read_text_and_json(transcript_root, monkeypatch):
    now = clock.parse_iso("2026-11-23T12:10:00Z")
    monkeypatch.setattr(clock, "utc_now", lambda: now)
    monkeypatch.setattr(
        "odsod_daemon.components.transcript.cli.local_zone", lambda: ZONE
    )
    append(transcript_root, "text", RECORDS[2])
    writer = Writer(TranscriptConfig())
    writer.flush(now)
    original = writer.path(now.date()).read_bytes()
    result = CliRunner().invoke(app, ["transcript"])
    assert result.exit_code == 0 and result.output == original.decode()
    result = CliRunner().invoke(app, ["transcript", "--day", "2026-11-23", "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert (
        body["day"] == "2026-11-23"
        and body["host"] == "test-host"
        and not body["finished"]
    )
    assert body["lines"][0] == {
        "time": "2026-11-23T13:01:00+01:00",
        "tag": "dic",
        "text": "Why does this work?",
        "key": "dic-first",
    }
    assert writer.path(now.date()).read_bytes() == original


def test_missing_day_and_invalid_day(transcript_root):
    runner = CliRunner()
    result = runner.invoke(app, ["transcript", "--day", "2020-01-01", "--json"])
    assert result.exit_code == 0 and json.loads(result.output)["lines"] == []
    assert runner.invoke(app, ["transcript", "--day", "bad"]).exit_code == 2


def test_note_pin_while_pipeline_down(transcript_root):
    runner = CliRunner()
    assert runner.invoke(app, ["note", "My note"]).exit_code == 0
    assert runner.invoke(app, ["pin"]).exit_code == 0
    writer = Writer(TranscriptConfig())
    writer.flush()
    lines = json.loads(runner.invoke(app, ["transcript", "--json"]).output)["lines"]
    assert [r["tag"] for r in lines] == ["nfo", "pin"]
