"""Pure interaction rules and batch ordering."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from odsod_daemon.components.interactions.batch import gate, process, records
from odsod_daemon.components.interactions.boundaries import detect
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import parse_front_matter
from odsod_daemon.components.interactions.lines import collect, skip
from odsod_daemon.components.interactions.render import filename, heading
from odsod_daemon.components.interactions.speakers import speaker
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
        dict(u, input=u["id"], outcome="ok", text="Hej hela världen")
        for u in [utterance(), line]
    ]
    texts.append(dict(input="dic", channel="dic", outcome="ok", text="SECRET"))
    b = boundary([utterance(), line], events)
    assert [line["name"] for line in collect(b, texts, events, C)] == ["Alice"]


def test_a_short_owner_reply_is_kept_next_to_matching_sys_text():
    events = [event("speaking", -1, names=["Alice"])]
    mic, sys = utterance(), utterance(channel="sys")
    texts = [
        dict(mic, input=mic["id"], outcome="ok", text="Yes."),
        dict(sys, input=sys["id"], outcome="ok", text="Yes, I think so too."),
    ]
    lines = collect(boundary([mic, sys], events), texts, events, C)
    assert [line["channel"] for line in lines] == ["mic", "sys"]


def test_gate():
    u = utterance()
    t = dict(input=u["id"])
    assert not gate([u], [], [])
    assert not gate([], [u], [])
    assert gate([u], [], [t])


SPEECH = dict(channel="mic", name="Owner", text="Hej")
NOTE = dict(channel="note", name="Note", text="Check numbers")


@pytest.mark.parametrize(
    "lines,limit,expected",
    [
        ([], 3, True),
        ([SPEECH] * 3, 3, True),
        ([SPEECH] * 4, 3, False),
        ([NOTE], 3, False),
        ([SPEECH, NOTE], 3, False),
        ([SPEECH], 0, False),
        ([], 0, True),
    ],
)
def test_interactions_ac17_skip_rule(lines, limit, expected):
    """PRD interactions AC-17: at most `skip_max_lines` speech lines and no
    note gives no document; any note or more speech gives one."""
    assert skip(lines, limit) is expected


STOCKHOLM = ZoneInfo("Europe/Stockholm")
START = datetime(2026, 11, 22, 14, 5, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Weekly sync", "2026-11-22-1505-laptop-weekly-sync.md"),
        ("Åsa: API / migration!", "2026-11-22-1505-laptop-asa-api-migration.md"),
        (
            "A very long meeting title that goes on and on and on",
            "2026-11-22-1505-laptop-a-very-long-meeting-title-that-goes-on-a.md",
        ),
        ("🎉🎉", "2026-11-22-1505-laptop.md"),
        ("   ", "2026-11-22-1505-laptop.md"),
        (None, "2026-11-22-1505-laptop.md"),
    ],
)
def test_interactions_ac16_file_name(title, expected):
    """PRD interactions AC-16: the file name holds the local start, the host
    and a slug of the meeting title; no usable title gives no slug."""
    assert filename(START, "laptop", title, STOCKHOLM) == expected


@pytest.mark.parametrize(
    "title,expected",
    [("Weekly sync", "Weekly sync"), (None, "Interaction 15:05")],
)
def test_interactions_ac16_heading(title, expected):
    """PRD interactions AC-16: the heading is the meeting title, else the
    local start time."""
    assert heading(title, START, STOCKHOLM) == expected


@pytest.mark.parametrize(
    "count,notes,expected",
    [(0, 0, "skipped"), (2, 0, "skipped"), (2, 1, "ok"), (10, 0, "ok")],
)
def test_skip_and_document(temp_root, count, notes, expected):
    us = [utterance(i * 11) for i in range(count)] or [utterance()]
    b = boundary(us)
    texts = [dict(u, input=u["id"], outcome="ok", text="Hej") for u in us[:count]]
    roots = paths.roots()
    events = [event("note", 5, text="Check numbers")] * notes
    process(b, texts, events, C, roots, "test", STOCKHOLM)
    result = records(roots.state / "interactions")[0]
    assert result["outcome"] == expected
    assert result["lines"] == count
    docs = list((roots.state / "documents/interactions").glob("*.md"))
    if expected == "ok":
        assert [d.name for d in docs] == ["2026-11-23-1100-test.md"]
        content = docs[0].read_text()
        meta = parse_front_matter(content)
        assert meta.timezone == "Europe/Stockholm"
        assert meta.start.endswith("+01:00")
        assert meta.title is None
        assert "\ntitle: null\n" in content
        assert "\n# Interaction 11:00\n\n## Transcript\n" in content
        assert "## Summary" not in content
        assert ("📝 **Note:** Check numbers" in content) is bool(notes)
        assert len(records(roots.state / "finished/interactions")) == 1
    else:
        assert not docs


def test_interactions_ac16_meeting_title_names_the_document(temp_root):
    """PRD interactions AC-16: a meeting title gives the title, the heading
    and the file name slug; a name taken by another interaction gets `-2`."""
    meeting = event("meeting-start", -60, platform="meet", code="x", title="Sync")
    one = utterance()
    b = boundary([one], [meeting])
    texts = [dict(u, input=u["id"], outcome="ok", text="Hej") for u in [one] * 4]
    roots = paths.roots()
    directory = roots.state / "documents/interactions"
    directory.mkdir(parents=True)
    (directory / "2026-11-23-1100-test-sync.md").write_text(
        "---\nid: other\ntype: interaction\nhost: test\nstart: x\nend: x\n"
        "timezone: UTC\n---\n"
    )
    process(b, texts, [meeting], C, roots, "test", STOCKHOLM)
    path = directory / "2026-11-23-1100-test-sync-2.md"
    content = path.read_text()
    assert parse_front_matter(content).title == "Sync"
    assert "\n# Sync\n\n## Transcript\n" in content
    assert records(roots.state / "interactions")[0]["document"] == path.name


@pytest.mark.parametrize("crash_directory", ["finished/interactions", "interactions"])
def test_crash(temp_root, monkeypatch, crash_directory):
    from odsod_daemon.components.interactions import batch

    b = boundary()
    text = [dict(utterance(), input="mic-0", outcome="ok", text="Hej")] * 4

    real_append = batch.append

    def crash(directory, record):
        if str(directory).endswith("/state/" + crash_directory):
            raise RuntimeError("crash")
        real_append(directory, record)

    monkeypatch.setattr(batch, "append", crash)
    with pytest.raises(RuntimeError):
        process(b, text, [], C, paths.roots(), "test", UTC)
    monkeypatch.setattr(batch, "append", real_append)
    process(b, text, [], C, paths.roots(), "test", UTC)
    assert len(list((temp_root / "state/documents/interactions").glob("*.md"))) == 1
    assert len(records(temp_root / "state/finished/interactions")) == 1


def test_capture_coverage_is_per_channel():
    # A mic stop cannot certify unprocessed sys audio as silence.
    cov = [dict(channel="mic", end=stamp(400)), dict(channel="sys", end=stamp(20))]
    capture = [event("stop", 20, channel="mic")]
    assert not detect([utterance()], [], cov, capture, NOW + timedelta(seconds=1000), C)


def test_front_matter_is_plain_yaml():
    """ADR-0016: front matter as in the ADR example, readable in Obsidian."""
    from datetime import UTC

    from odsod_daemon.components.interactions.contract import (
        InteractionDocument,
        parse_front_matter,
    )
    from odsod_daemon.components.interactions.render import render

    meta = InteractionDocument.model_validate(
        dict(
            type="interaction",
            id="20261122T140000.000Z",
            host="work-laptop",
            start="2026-11-22T15:00:00.000+01:00",
            end="2026-11-22T15:42:10.500+01:00",
            timezone="Europe/Stockholm",
            meeting=None,
            participants=["Owner Name", "Åsa Exempel"],
            title="API: migration plan",
        )
    )
    text = render(meta, "API: migration plan", [], UTC)
    head = text.split("\n---\n", 1)[0]
    assert "{" not in head and '"id"' not in head
    assert "title: 'API: migration plan'" in head
    assert "- Åsa Exempel" in head
    assert parse_front_matter(text) == meta


def test_document_lines_carry_the_utterance_id_and_what_asr_heard():
    """PRD interactions AC-15: each speech line names its utterance; a line
    that cleanup changed also keeps the ASR text, both hidden in Markdown."""
    from odsod_daemon.components.interactions.render import transcript

    base = {"ts": "2026-11-22T14:00:05.000Z", "at": "2026-11-22T14:00:05.000Z"}
    lines = [
        dict(base, input="sys-a", channel="sys", name="Alice", text="Use Clerk."),
        dict(
            base,
            input="sys-b",
            channel="sys",
            name="Bob",
            text="Yes.",
            heard="Use Klerk -- now",
        ),
        dict(
            base,
            channel="note",
            name="Note",
            text="check it",
            ts="2026-11-22T14:00:05.000Z",
        ),
    ]
    zone = ZoneInfo("Europe/Stockholm")
    out = transcript(lines, zone, True).splitlines()
    assert out[0] == "[15:00:05] **Alice:** Use Clerk. <!-- id:sys-a -->"
    assert (
        out[1] == "[15:00:05] **Bob:** Yes. <!-- id:sys-b heard: Use Klerk - - now -->"
    )
    assert out[2] == "[15:00:05] 📝 **Note:** check it"
    assert "<!--" not in transcript(lines, zone)


def _meta(b, lines, events=()):
    from odsod_daemon.components.interactions.render import metadata

    return metadata(b, lines, list(events), "host", UTC)


def test_meeting_block_keeps_platform_code_and_title_only():
    """ADR-0016: `meeting` holds platform, code and title, not raw event fields."""
    start = event(
        "meeting-start",
        -60,
        platform="meet",
        code="x",
        title="Sync",
        url="https://example.invalid/x",
    )
    b = boundary([utterance()], [start])
    meta = _meta(b, [])
    assert meta.meeting is not None
    assert meta.meeting.model_dump() == {
        "platform": "meet",
        "code": "x",
        "title": "Sync",
    }


def test_participants_leave_out_the_placeholders():
    """PRD interactions: participants are people; `Others` and the unset owner
    name are labels, not names."""
    lines = [
        dict(name=C.owner_name, channel="mic"),
        dict(name="Others", channel="sys"),
        dict(name="Alice Example", channel="sys"),
    ]
    assert _meta(boundary(), lines).participants == ["Alice Example"]


def test_first_interaction_of_a_meeting_starts_at_the_meeting_start():
    """ADR-0016: in a meeting, the first interaction starts when the meeting
    starts; a later one in the same meeting starts at its first speech."""
    start = event("meeting-start", 0, platform="meet", code="x", title="Sync")
    first, second = detect(
        [utterance(120), utterance(400)],
        [start, event("pin", 300)],
        coverage(2000),
        [],
        NOW,
        C,
    )[:2]
    assert _meta(first, []).start == NOW.isoformat(timespec="milliseconds")
    assert first.id == "20261123T100200.000Z"
    later = NOW + timedelta(seconds=400)
    assert _meta(second, []).start == later.isoformat(timespec="milliseconds")
