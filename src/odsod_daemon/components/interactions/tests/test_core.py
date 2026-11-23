"""Pure interaction rules and batch ordering."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from odsod_daemon.components.interactions.batch import gate, process, records
from odsod_daemon.components.interactions.boundaries import detect
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import parse_front_matter
from odsod_daemon.components.interactions.lines import collect
from odsod_daemon.components.interactions.speakers import speaker
from odsod_daemon.components.interactions.summarize import Summary, chunks, validate
from odsod_daemon.lib import clock, paths

NOW = datetime(2026, 11, 23, 10, tzinfo=UTC)
C = InteractionsConfig()


def stamp(seconds=0):
    return clock.iso(NOW + timedelta(seconds=seconds))


def utterance(seconds=0, channel="mic"):
    return dict(
        ts=stamp(seconds),
        kind="utterance",
        id=f"{channel}-{seconds}",
        start=stamp(seconds),
        end=stamp(seconds + 10),
        channel=channel,
    )


def event(kind, seconds=0, **extra):
    return dict(ts=stamp(seconds), at=stamp(seconds), kind=kind, **extra)


def coverage(seconds=1000):
    return [dict(channel=c, end=stamp(seconds)) for c in ("mic", "sys")]


def boundary(utterances=None, events=None):
    return detect(utterances or [utterance()], events or [], coverage(), [], NOW, C)[0]


@pytest.mark.parametrize(
    "events,us,cov,capture,expected",
    [
        ([], [utterance(), utterance(310)], [], [], ["silence"]),
        ([], [utterance()], [], [], []),
        ([], [utterance()], coverage(310), [], ["silence"]),
        ([event("pin", 20)], [utterance()], coverage(20), [], ["pin"]),
        (
            [event("meeting-start", 20, platform="meet", code="x")],
            [utterance()],
            coverage(20),
            [],
            ["meeting"],
        ),
        ([], [utterance()], coverage(20), [event("stop", 20)], ["silence"]),
        (
            [],
            [utterance()],
            coverage(20),
            [event("start", 400, prev_end=stamp(20), audio_start=stamp(400))],
            ["silence"],
        ),
        (
            [],
            [utterance()],
            coverage(20),
            [event("gap", 20, start=stamp(20), end=stamp(400))],
            ["silence"],
        ),
    ],
)
def test_boundaries(events, us, cov, capture, expected):
    found = detect(us, events, cov, capture, NOW + timedelta(seconds=1000), C)
    assert [b.end_cause for b in found] == expected
    if found:
        assert found[0].end == clock.parse_iso(us[0]["end"])


def test_profile_and_pin_before_speech():
    events = [event("meeting-start", -1, platform="meet", code="x"), event("pin", -2)]
    assert not detect([utterance()], events, coverage(70), [], NOW, C)
    config = InteractionsConfig(meeting_cutoffs={"x": 60})
    assert (
        detect([utterance()], events, coverage(70), [], NOW, config)[0].end_cause
        == "silence"
    )


def test_speakers_and_echo():
    meeting = event("meeting-start", -10, platform="meet", code="x", title="Sync")
    events = [
        meeting,
        event("speaking", -1, platform="meet", code="x", names=["Owner", "Alice"]),
        event("speaking", 8, platform="meet", code="x", names=["Bob"]),
    ]
    line = utterance(channel="sys")
    assert speaker(line, meeting, events, C) == "Alice"
    assert speaker(line, None, events, C) == "Others"
    texts = [
        dict(u, input=u["id"], outcome="ok", text="Hej världen")
        for u in [utterance(), line]
    ]
    texts.append(dict(input="dic", channel="dic", outcome="ok", text="SECRET"))
    b = boundary([utterance(), line], events)
    assert [line["name"] for line in collect(b, texts, events, C)] == ["Alice"]


def test_validation_and_chunks():
    reply = dict(
        skip=False,
        title="one two three four five six seven eight nine",
        overview="One. Two. Three. Four. Five.",
        points=[
            dict(label="Wrong", text="bad", owner=None),
            dict(label="Next", text="", owner=None),
        ],
    )
    result = validate("<think>secret</think>" + json.dumps(reply))
    assert len(result.title.split()) == 8
    assert result.overview == "One. Two. Three."
    assert result.points == []
    assert chunks("abc\ndef\nxyz", 8) == ["abc\ndef\n", "xyz"]
    with pytest.raises(ValueError):
        chunks("long line", 3)
    with pytest.raises(ValueError):
        validate("bad JSON")


def test_gate():
    u = utterance()
    t = dict(input=u["id"])
    assert not gate([u], [], [], True, True)
    assert not gate([], [u], [], True, True)
    assert not gate([u], [], [t], False, True)
    assert not gate([u], [], [t], True, False)
    assert gate([u], [], [t], True, True)


@pytest.mark.parametrize(
    "count,skip,expected",
    [(0, False, "skipped"), (2, True, "skipped"), (10, True, "ok")],
)
async def test_skip_and_document(temp_root, count, skip, expected):
    us = [utterance(i * 11) for i in range(count)] or [utterance()]
    b = boundary(us)
    texts = [dict(u, input=u["id"], outcome="ok", text="Hej") for u in us[:count]]
    calls = []

    async def summarize(text):
        calls.append(text)
        return Summary(
            skip=skip, title="Title", overview="Overview.", points=[]
        ), "test"

    roots = paths.roots()
    notes = [event("note", 5, text="Check numbers")]
    await process(
        b, texts, notes, C, roots, "test", ZoneInfo("Europe/Stockholm"), summarize
    )
    result = records(roots.state / "interactions")[0]
    assert result["outcome"] == expected
    assert bool(calls) == bool(count)
    docs = list((roots.state / "documents/interactions").glob("*.md"))
    if expected == "ok":
        content = docs[0].read_text()
        meta = parse_front_matter(content)
        assert meta.timezone == "Europe/Stockholm"
        assert meta.start.endswith("+01:00")
        assert "📝 **Note:** Check numbers" in content
        assert len(records(roots.state / "finished/interactions")) == 1
    else:
        assert not docs


@pytest.mark.parametrize("crash_directory", ["finished/interactions", "interactions"])
async def test_crash(temp_root, monkeypatch, crash_directory):
    from odsod_daemon.components.interactions import batch

    b = boundary()
    text = [dict(utterance(), input="mic-0", outcome="ok", text="Hej")]
    calls = []

    async def summarize(text):
        calls.append(text)
        return Summary(
            skip=False, title="Title", overview="Overview.", points=[]
        ), "test"

    real_append = batch.append

    def crash(directory, record):
        if str(directory).endswith("/state/" + crash_directory):
            raise RuntimeError("crash")
        real_append(directory, record)

    monkeypatch.setattr(batch, "append", crash)
    with pytest.raises(RuntimeError):
        await process(b, text, [], C, paths.roots(), "test", UTC, summarize)
    monkeypatch.setattr(batch, "append", real_append)
    await process(b, text, [], C, paths.roots(), "test", UTC, summarize)
    assert len(calls) == 1
    assert len(list((temp_root / "state/documents/interactions").glob("*.md"))) == 1
    assert len(records(temp_root / "state/finished/interactions")) == 1
