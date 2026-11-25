import asyncio
from datetime import timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.components.transcript.contract import parse_file
from odsod_daemon.components.transcript.tests.conftest import append
from odsod_daemon.components.transcript.tests.test_core import RECORDS, ZONE
from odsod_daemon.components.transcript.writer import Writer, run
from odsod_daemon.lib import clock, streams

NOW = clock.parse_iso("2026-11-23T12:10:00Z")


def read(writer, day=None):
    day = day or NOW.astimezone(ZONE).date()
    return parse_file(writer.path(day).read_text())


def test_restart_and_partial_line(transcript_root):
    for record in RECORDS:
        stream = (
            "text"
            if record["kind"] == "text"
            else "events/user"
            if record["kind"] in ("note", "pin")
            else "events/signals"
        )
        append(transcript_root, stream, record)
    writer = Writer(TranscriptConfig())
    writer.flush(NOW)
    before = read(writer)
    assert len(before) == 7
    path = writer.path(NOW.astimezone(ZONE).date())
    with path.open("ab") as handle:
        handle.write(b"[13:00:00] partial")
    restarted = Writer(TranscriptConfig())
    restarted.flush(NOW)
    assert read(restarted) == before
    assert path.read_bytes().endswith(b"\n")


def test_restart_skips_old_finished_transcript(transcript_root, monkeypatch):
    monkeypatch.setattr(clock, "utc_now", lambda: NOW)
    writer = Writer(TranscriptConfig())
    old_day = NOW.date() - timedelta(days=writer.retention + 2)
    path = writer.path(old_day)
    path.parent.mkdir(parents=True, exist_ok=True)
    original = b"finished transcript without a final newline"
    path.write_bytes(original)
    append(
        transcript_root,
        "finished/transcript",
        {
            "kind": "finished",
            "ts": clock.iso(NOW - timedelta(days=writer.retention + 2)),
            "document": path.name,
            "type": "transcripts",
            "day": old_day.isoformat(),
            "capped": False,
        },
    )
    read_bytes = Path.read_bytes

    def guard_read(file):
        assert file != path, "recovery must not read a finished transcript"
        return read_bytes(file)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", guard_read)
        restarted = Writer(TranscriptConfig())
    assert path.name in restarted.closed
    assert old_day not in restarted.keys
    assert path.read_bytes() == original


def test_silence_has_no_file(transcript_root):
    for n in range(3600):
        record = {**RECORDS[0], "input": str(n), "outcome": "empty"}
        append(transcript_root, "text", record)
    writer = Writer(TranscriptConfig())
    writer.flush(NOW)
    assert not list(writer.directory.glob("*.md"))


def test_backlog_keeps_own_times_and_arrival_order(transcript_root):
    # Older ambient speech arrives after dictation, as in the speech queue.
    for record in (RECORDS[2], RECORDS[0]):
        append(
            transcript_root,
            "text",
            {**record, "ts": clock.iso(NOW + timedelta(seconds=record == RECORDS[0]))},
        )
    writer = Writer(TranscriptConfig())
    writer.flush(NOW + timedelta(seconds=2))
    output = read(writer)
    assert [r.tag for r in output] == ["dic", "sys"]
    assert [r.time.minute for r in output] == [1, 0]


def test_echo_wait_then_coverage_and_sys_text(transcript_root):
    mic = RECORDS[1]
    append(transcript_root, "text", mic)
    writer = Writer(TranscriptConfig())
    now = clock.parse_iso(mic["ts"])
    writer.flush(now)
    assert not list(writer.directory.glob("*.md"))
    append(
        transcript_root,
        "coverage",
        {
            "kind": "covered",
            "channel": "sys",
            "ts": clock.iso(now),
            "end": clock.iso(now + timedelta(seconds=5)),
        },
    )
    append(transcript_root, "text", RECORDS[0])
    writer.flush(now + timedelta(seconds=1))
    assert [r.tag for r in read(writer)] == ["sys"]


def test_finish_once_and_ignore_late_text(transcript_root):
    day = NOW.astimezone(ZONE).date()
    from odsod_daemon.components.transcript.days import bounds

    _, end = bounds(day, ZONE)
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
    writer = Writer(TranscriptConfig())
    writer.flush(end + timedelta(seconds=61))
    contents = writer.path(day).read_bytes()
    finished = streams.read_day(
        streams.day_path(transcript_root / "state/finished/transcript", end.date())
    )
    assert len(finished) == 1 and not finished[0]["capped"]
    append(
        transcript_root,
        "text",
        {**RECORDS[2], "ts": clock.iso(end + timedelta(seconds=62))},
    )
    writer = Writer(TranscriptConfig())
    writer.flush(end + timedelta(seconds=63))
    assert writer.path(day).read_bytes() == contents
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


def test_cap_pending_and_no_write_after_finish(transcript_root, monkeypatch):
    from odsod_daemon.components.transcript.days import bounds

    day = NOW.astimezone(ZONE).date()
    _, end = bounds(day, ZONE)
    utterance = {
        "kind": "utterance",
        "ts": RECORDS[0]["ts"],
        "id": "lost",
        "channel": "sys",
        "start": RECORDS[0]["start"],
        "end": RECORDS[0]["end"],
    }
    append(transcript_root, "utterances/ambient", utterance)
    writer = Writer(TranscriptConfig())
    writer.flush(end + timedelta(hours=48))
    output = read(writer)
    assert (
        len(output) == 1
        and output[0].key == "untx:lost"
        and "(finish-cap)" in output[0].text
    )
    original = writer.path(day).read_bytes()
    monkeypatch.setattr(clock, "utc_now", lambda: end + timedelta(hours=48, seconds=1))
    append(transcript_root, "text", {**RECORDS[0], "input": "lost"})
    Writer(TranscriptConfig()).flush(end + timedelta(hours=48, seconds=1))
    assert writer.path(day).read_bytes() == original


@pytest.mark.looptime(False)
async def test_live_missing_signals_does_not_block(transcript_root):
    settings = TranscriptConfig()
    record = {**RECORDS[2], "ts": clock.iso(), "start": clock.iso()}
    service = asyncio.create_task(run(settings))
    try:
        await clock.sleep(0.05)
        append(transcript_root, "text", record)
        path = (
            transcript_root
            / "state/documents/transcripts"
            / f"{clock.utc_now().astimezone(ZONE).date()}-test-host.md"
        )
        async with clock.timeout(3):
            while not path.exists():
                await clock.sleep(0.01)
        assert parse_file(path.read_text())[0].key == record["input"]
        assert not list((transcript_root / "state/events/signals").glob("*.jsonl"))
    finally:
        service.cancel()
        await asyncio.gather(service, return_exceptions=True)


def test_hour_backlog_after_outage(transcript_root):
    for n in range(3600):
        start = NOW + timedelta(seconds=n)
        record = {
            **RECORDS[0],
            "input": f"sys-{n}",
            "start": clock.iso(start),
            "end": clock.iso(start + timedelta(seconds=1)),
            "ts": clock.iso(NOW + timedelta(hours=2)),
        }
        append(transcript_root, "text", record)
    writer = Writer(TranscriptConfig())
    writer.flush(NOW + timedelta(hours=2))
    output = read(writer)
    assert len(output) == 3600
    assert output[0].time == NOW.astimezone(ZONE)
    assert output[-1].time == (NOW + timedelta(seconds=3599)).astimezone(ZONE)
    Writer(TranscriptConfig()).flush(NOW + timedelta(hours=2))
    assert len(read(writer)) == 3600


def test_crash_after_last_line_before_finish(transcript_root, monkeypatch):
    from odsod_daemon.components.transcript.days import bounds

    day = NOW.astimezone(ZONE).date()
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
    original_append = streams.append

    def crash(path, record):
        if "finished" in path.parts:
            raise RuntimeError("kill before finish")
        original_append(path, record)

    monkeypatch.setattr(streams, "append", crash)
    with pytest.raises(RuntimeError, match="kill"):
        Writer(TranscriptConfig()).flush()
    monkeypatch.setattr(streams, "append", original_append)
    writer = Writer(TranscriptConfig())
    writer.flush()
    assert len(read(writer)) == 1
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


def test_open_gap_across_midnight_gives_one_line_per_day(transcript_root):
    from odsod_daemon.components.transcript.days import bounds

    day = NOW.astimezone(ZONE).date()
    _, end = bounds(day, ZONE)
    stop = end - timedelta(minutes=30)
    append(transcript_root, "text", RECORDS[0])
    for channel in ("mic", "sys"):
        append(
            transcript_root,
            "coverage",
            {
                "kind": "covered",
                "channel": channel,
                "ts": clock.iso(stop),
                "end": clock.iso(stop),
            },
        )
        append(
            transcript_root,
            "events/capture",
            {"kind": "stop", "channel": channel, "ts": clock.iso(stop)},
        )

    writer = Writer(TranscriptConfig())
    writer.flush(end + timedelta(seconds=61))
    writer.flush(end + timedelta(seconds=120))

    finished = streams.read_day(
        streams.day_path(transcript_root / "state/finished/transcript", end.date())
    )
    assert len(finished) == 1
    gap_lines = [line for line in read(writer, day) if line.tag == "gap"]
    assert [line.text for line in gap_lines] == [
        "not recording 23:30:00\u201300:00:00 (logout)"
    ]
    contents = writer.path(day).read_bytes()

    morning = end + timedelta(hours=7)
    for channel in ("mic", "sys"):
        append(
            transcript_root,
            "events/capture",
            {
                "kind": "start",
                "channel": channel,
                "ts": clock.iso(morning),
                "audio_start": clock.iso(morning),
                "prev_end": clock.iso(stop - timedelta(milliseconds=500)),
            },
        )
    Writer(TranscriptConfig()).flush(morning + timedelta(seconds=5))
    restarted = Writer(TranscriptConfig())
    restarted.flush(morning + timedelta(seconds=10))

    assert writer.path(day).read_bytes() == contents
    next_day = [
        line
        for line in read(restarted, end.astimezone(ZONE).date())
        if line.tag == "gap"
    ]
    assert [line.text for line in next_day] == [
        "not recording 00:00:00\u201307:00:00 (logout)"
    ]


def test_dropped_echo_is_decided_once(transcript_root, monkeypatch):
    """A drop is final. Deciding it again on every flush cost the live pipeline
    about half a core by afternoon (2026-11-25)."""
    from odsod_daemon.components.transcript import echo

    mic = RECORDS[1]
    now = clock.parse_iso(mic["ts"])
    append(transcript_root, "text", mic)
    append(
        transcript_root,
        "coverage",
        {
            "kind": "covered",
            "channel": "sys",
            "ts": clock.iso(now),
            "end": clock.iso(now + timedelta(seconds=5)),
        },
    )
    append(transcript_root, "text", RECORDS[0])
    writer = Writer(TranscriptConfig())
    writer.flush(now + timedelta(seconds=1))
    assert [r.tag for r in read(writer)] == ["sys"]
    calls = []
    decide = echo.decide
    monkeypatch.setattr(echo, "decide", lambda *a: calls.append(1) or decide(*a))
    writer.flush(now + timedelta(seconds=2))
    assert calls == []
    assert [r.tag for r in read(writer)] == ["sys"]
