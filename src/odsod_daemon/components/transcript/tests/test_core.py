import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from odsod_daemon.components.transcript import days, echo, gaps, lines
from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.components.transcript.contract import parse_file, parse_line
from odsod_daemon.lib import clock

ZONE = ZoneInfo("Europe/Stockholm")
CONFIG = TranscriptConfig()
RECORDS = json.loads((Path(__file__).parent / "testdata/records.json").read_text())


@pytest.mark.parametrize(
    "index,tag,hour",
    [
        (0, "sys", 13),
        (1, "mic", 13),
        (2, "dic", 13),
        (3, "nfo", 13),
        (4, "pin", 13),
        (5, "mtg", 13),
        (6, "mtg", 13),
    ],
)
def test_lines(index, tag, hour):
    line = lines.from_record(RECORDS[index], ZONE)
    assert line is not None
    assert line.tag == tag and line.time.hour == hour
    rendered = line.render()
    assert rendered.count("<!--") == 1 and "\n" not in rendered
    parsed = parse_line(rendered, line.time.date(), ZONE)
    assert parsed is not None and parsed.key == line.key
    assert parsed.time == line.time
    if index == 5:
        assert line.text == "started: Daily (meet abc-defg-hij)"
    if index == 6:
        assert line.text == "ended: meet abc-defg-hij"


@pytest.mark.parametrize(
    "outcome,expected", [("empty", None), ("failed", "gap"), ("expired", "gap")]
)
def test_outcomes(outcome, expected):
    line = lines.from_record({**RECORDS[0], "outcome": outcome}, ZONE)
    assert (line.tag if line else None) == expected
    if line:
        assert outcome in line.text and line.key == "untx:sys-first"


def test_parser_ignores_partial_line():
    line = lines.from_record(RECORDS[0], ZONE)
    assert line is not None
    header = (
        "---\ntype: transcript\nhost: test\ndate: 2026-11-23\n"
        "timezone: Europe/Stockholm\n---\n"
    )
    assert len(parse_file(header + line.render() + "\n" + line.render())) == 1


@pytest.mark.parametrize(
    "day,hours",
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25), (date(2026, 11, 23), 24)],
)
def test_local_days(day, hours):
    start, end = days.bounds(day, ZONE)
    assert (end - start).total_seconds() == hours * 3600
    assert days.assigned({"start": clock.iso(start)}, day, ZONE)
    assert not days.assigned({"start": clock.iso(end)}, day, ZONE)


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("echo", "drop"),
        ("different", "keep"),
        ("short", "keep"),
        ("coverage", "hold"),
        ("pending", "hold"),
        ("expired", "keep"),
        ("split", "drop"),
    ],
)
def test_echo(scenario, expected):
    mic = dict(RECORDS[1])
    text = [dict(RECORDS[0])]
    utterances = []
    coverage = {"sys": clock.parse_iso(mic["end"]) + timedelta(seconds=2)}
    now = clock.parse_iso(mic["ts"])
    if scenario == "different":
        mic["text"] = "I have a completely different question"
    if scenario == "short":
        mic["text"] = "Hello"
    if scenario in ("coverage", "expired"):
        coverage = {}
    if scenario == "expired":
        now += timedelta(seconds=120)
    if scenario == "pending":
        utterances = [
            {
                "id": "pending",
                "channel": "sys",
                "start": mic["start"],
                "end": mic["end"],
            }
        ]
    if scenario == "split":
        mic["text"] = "alpha beta gamma delta epsilon zeta"
        text = [
            {**text[0], "text": "alpha beta gamma"},
            {**text[0], "input": "sys-two", "text": "delta epsilon zeta"},
        ]
    assert echo.decide(mic, utterances, text, coverage, now, CONFIG) == expected


def capture(start, end, channel="mic", **extra):
    return {
        "kind": "start",
        "ts": clock.iso(end),
        "audio_start": clock.iso(end),
        "prev_end": clock.iso(start),
        "channel": channel,
        **extra,
    }


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("restart", "restart"),
        ("pause", "pause"),
        ("logout", "logout"),
        ("unknown", "unknown"),
        ("suspend", "suspend"),
    ],
)
def test_gap_causes(scenario, expected):
    start = clock.parse_iso("2026-11-23T12:00:00Z")
    end = start + timedelta(seconds=120 if scenario == "restart" else 600)
    records = [capture(start, end), capture(start, end, "sys")]
    user = []
    if scenario == "pause":
        user = [{"kind": "pause", "ts": clock.iso(start - timedelta(seconds=10))}]
    if scenario == "logout":
        records.append({"kind": "stop", "channel": "mic", "ts": clock.iso(start)})
    if scenario == "suspend":
        records = [
            {
                "kind": "gap",
                "channel": "sys",
                "ts": clock.iso(end),
                "start": clock.iso(start),
                "end": clock.iso(end),
                "reason": "suspend",
            }
        ]
    off = gaps.ranges(records, end)
    output = gaps.lines(off, user, records, CONFIG, ZONE)
    assert len(output) == 1 and f"({expected})" in output[0].text
    assert ("not recording sys" in output[0].text) == (scenario == "suspend")


def test_midnight_gap_and_open_logout():
    start = clock.parse_iso("2026-11-23T22:55:00Z")
    now = start + timedelta(minutes=10)
    capture_records = [
        {"kind": "stop", "channel": ch, "ts": clock.iso(start)} for ch in ("mic", "sys")
    ]
    off = gaps.ranges(capture_records, now)
    output = gaps.lines(off, [], capture_records, CONFIG, ZONE)
    # The open range gives the finished day its pre-midnight line only.
    assert [line.text for line in output] == [
        "not recording 23:55:00\u201300:00:00 (logout)"
    ]
    assert (
        days.finish(
            date(2026, 11, 23),
            ZONE,
            now,
            {"mic": start, "sys": start},
            off,
            [],
            False,
            CONFIG,
        )
        == "ready"
    )
    prev_end = start - timedelta(milliseconds=500)
    closed = gaps.ranges(
        capture_records + [capture(prev_end, now, ch) for ch in ("mic", "sys")], now
    )
    closed_output = gaps.lines(closed, [], capture_records, CONFIG, ZONE)
    assert len(closed_output) == 2
    assert len({line.time.date() for line in closed_output}) == 2
    assert closed_output[0].key == output[0].key
    assert closed_output[1].key == "gap:2026-11-23T23:00:00.000Z"
    assert "23:54:59\u201300:00:00" in closed_output[0].text


@pytest.mark.parametrize(
    "delay,closed,expected",
    [
        (0.5, False, "ready"),
        (5, False, "ready"),
        (5.001, False, None),
        (0.5, True, None),
    ],
)
def test_finish_stop_after_last_sample(delay, closed, expected):
    day = date(2026, 11, 23)
    _, end = days.bounds(day, ZONE)
    covered = end - timedelta(hours=1)
    now = end + timedelta(seconds=61)
    off = [
        gaps.OffRange(
            covered + timedelta(seconds=delay),
            now,
            frozenset(["mic", "sys"]),
            closed=closed,
        )
    ]
    assert (
        days.finish(
            day, ZONE, now, {"mic": covered, "sys": covered}, off, [], False, CONFIG
        )
        == expected
    )


@pytest.mark.parametrize("blocked", ["pending", "held", "coverage", "settle", "none"])
def test_finish(blocked):
    day = date(2026, 11, 23)
    _, end = days.bounds(day, ZONE)
    now = end + timedelta(seconds=61)
    coverage = {"mic": end, "sys": end}
    pending = [{"id": "pending"}] if blocked == "pending" else []
    if blocked == "coverage":
        coverage.pop("sys")
    if blocked == "settle":
        now = end + timedelta(seconds=59)
    assert days.finish(
        day, ZONE, now, coverage, [], pending, blocked == "held", CONFIG
    ) == ("ready" if blocked == "none" else None)
    assert (
        days.finish(day, ZONE, end + timedelta(hours=48), {}, [], pending, True, CONFIG)
        == "cap"
    )


def test_pending_and_cap_merge():
    start = datetime(2026, 11, 23, 12, tzinfo=UTC)
    records = [
        {
            "id": f"mic-{n}",
            "channel": "mic",
            "start": clock.iso(start + timedelta(seconds=n)),
            "end": clock.iso(start + timedelta(seconds=n + 1)),
        }
        for n in range(3)
    ]
    pending = days.missing(start.date(), ZONE, records, [{"input": "mic-2"}])
    assert len(pending) == 2
    capped = days.capped_lines(pending, ZONE)
    assert len(capped) == 1 and capped[0].key == "untx:mic-0"
    assert "13:00:00\u201313:00:02 (finish-cap)" in capped[0].text


def test_cap_only_merges_adjacent_instants():
    pending = [
        {
            "id": "first",
            "channel": "sys",
            "start": "2026-11-23T12:00:00Z",
            "end": "2026-11-23T12:00:01Z",
        },
        {
            "id": "second",
            "channel": "sys",
            "start": "2026-11-23T12:00:01.500Z",
            "end": "2026-11-23T12:00:02Z",
        },
    ]
    assert len(days.capped_lines(pending, ZONE)) == 2


def test_open_range_is_never_a_restart():
    start = clock.parse_iso("2026-11-23T22:58:00Z")
    stops = [{"kind": "stop", "channel": "mic", "ts": clock.iso(start)}]
    [item] = gaps.ranges(stops, start + timedelta(minutes=2))
    assert gaps.cause(item, [], stops, CONFIG) == "logout"
