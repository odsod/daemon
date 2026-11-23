from datetime import timedelta

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.components.transcript.contract import parse_file
from odsod_daemon.components.transcript.days import bounds
from odsod_daemon.components.transcript.tests.conftest import append
from odsod_daemon.components.transcript.tests.test_core import RECORDS, ZONE
from odsod_daemon.components.transcript.writer import Writer, run
from odsod_daemon.lib import clock, streams


async def test_once_leaves_mic_held(transcript_root, monkeypatch):
    now = clock.parse_iso(RECORDS[1]["ts"])
    monkeypatch.setattr(clock, "utc_now", lambda: now)
    append(transcript_root, "text", RECORDS[1])
    append(transcript_root, "text", RECORDS[2])
    await run(TranscriptConfig(), once=True)
    writer = Writer(TranscriptConfig())
    output = parse_file(writer.path(now.date()).read_text())
    assert [line.tag for line in output] == ["dic"]
    original = writer.path(now.date()).read_bytes()
    await run(TranscriptConfig(), once=True)
    assert writer.path(now.date()).read_bytes() == original
    monkeypatch.setattr(clock, "utc_now", lambda: now + timedelta(seconds=120))
    await run(TranscriptConfig(), once=True)
    assert [line.tag for line in parse_file(writer.path(now.date()).read_text())] == [
        "dic",
        "mic",
    ]


def test_cli_once_finishes_eligible_day(transcript_root, monkeypatch):
    day = clock.parse_iso(RECORDS[0]["start"]).astimezone(ZONE).date()
    _, end = bounds(day, ZONE)
    monkeypatch.setattr(clock, "utc_now", lambda: end + timedelta(seconds=61))
    append(transcript_root, "text", RECORDS[0])
    for channel in ("mic", "sys"):
        append(
            transcript_root,
            "coverage",
            {
                "kind": "covered",
                "channel": channel,
                "ts": clock.iso(end),
                "end": clock.iso(end),
            },
        )
    result = CliRunner().invoke(app, ["run", "transcript", "--once"])
    assert result.exit_code == 0, result.output
    output = streams.read_day(
        streams.day_path(transcript_root / "state/finished/transcript", end.date())
    )
    assert len(output) == 1
    assert CliRunner().invoke(app, ["run", "transcript", "--once"]).exit_code == 0
    assert (
        len(
            streams.read_day(
                streams.day_path(
                    transcript_root / "state/finished/transcript", end.date()
                )
            )
        )
        == 1
    )
