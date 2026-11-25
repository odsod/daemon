"""Interaction documents through file contracts and the CLI."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.cleanup.contract import TextRecord
from odsod_daemon.components.interactions.contract import (
    FinishedInteraction,
    InteractionRecord,
    parse_front_matter,
)
from odsod_daemon.components.note.contract import Note
from odsod_daemon.components.segmentation.contract import (
    AmbientUtterance,
    Channel,
    Covered,
)
from odsod_daemon.components.signals.contract import (
    MeetingEnd,
    MeetingStart,
    Participants,
    Speaking,
)
from odsod_daemon.components.transcript.contract import FinishedTranscript
from odsod_daemon.lib import clock, power, streams


def seed(root: Path):
    now = clock.utc_now()
    start = now - timedelta(minutes=15)

    def stamp(seconds=0):
        return clock.iso(start + timedelta(seconds=seconds))

    day = start.date()

    def write(source, record):
        streams.append(
            streams.day_path(root / "state" / source, day),
            record.model_dump(mode="json"),
        )

    (root / "config/config.json").write_text(
        json.dumps(
            {
                "common": {
                    "host": "test-host",
                    "inference": {
                        # Nothing listens here: interactions call no LLM.
                        "llama_url": "http://127.0.0.1:9/v1/chat/completions",
                        "whisper_url": "http://localhost:8178",
                    },
                },
                "interactions": {
                    "owner_name": "Oscar",
                    "owner_aliases": ["Oscar Tile"],
                },
            }
        )
    )
    meeting: dict[str, Any] = dict(platform="meet", code="abc-defg-hij")
    write(
        "events/signals",
        MeetingStart(ts=stamp(-1), at=stamp(-1), title="Weekly sync", **meeting),
    )
    write(
        "events/signals",
        Participants(ts=stamp(), names=["Oscar", "Alice", "Bob"], **meeting),
    )
    write(
        "events/signals",
        Speaking(ts=stamp(), at=stamp(), names=["Oscar Tile", "Alice"], **meeting),
    )
    write("events/signals", Speaking(ts=stamp(30), at=stamp(30), names=[], **meeting))
    write(
        "events/signals", Speaking(ts=stamp(40), at=stamp(40), names=["Bob"], **meeting)
    )
    for i, (channel, text) in enumerate(
        [
            ("mic", "Vi behöver flytta databasen till Postgres."),
            ("sys", "Partitionerna orsakar luckor."),
            ("mic", "Jag kontrollerar mätvärdena."),
            ("sys", "Jag skriver planen i morgon."),
            ("sys", "Vi testar först på fredag."),
        ]
    ):
        u = AmbientUtterance(
            ts=stamp(i * 20),
            id=f"{i}-{channel}",
            channel=cast(Channel, channel),
            start=stamp(i * 20),
            end=stamp(i * 20 + 8),
        )
        write("utterances/ambient", u)
        write(
            "text",
            TextRecord(
                ts=u.ts,
                input=u.id,
                outcome="ok",
                channel=channel,
                start=u.start,
                end=u.end,
                text=text,
            ),
        )
    write("events/user", Note(ts=stamp(25), text="check the CDC lag numbers"))
    # Dictation is complete for the gate, but must never enter a document.
    dic = dict(
        ts=stamp(15),
        kind="utterance",
        id="dictation-private",
        channel="dic",
        start=stamp(15),
        end=stamp(18),
    )
    streams.append(streams.day_path(root / "state/utterances/dictation", day), dic)
    write(
        "text",
        TextRecord(
            ts=stamp(18),
            input=dic["id"],
            outcome="ok",
            channel="dic",
            start=dic["start"],
            end=dic["end"],
            text="PRIVATE DICTATION",
        ),
    )
    write("events/signals", MeetingEnd(ts=stamp(90), at=stamp(90), **meeting))
    for channel in ("mic", "sys"):
        write(
            "coverage", Covered(ts=clock.iso(now), channel=channel, end=clock.iso(now))
        )
    # The transcript worker runs in parallel. Its contract is a fixture here.
    transcript = root / "state/documents/transcripts/fixture.md"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("Fixture daily transcript.\n")
    write(
        "finished/transcripts",
        FinishedTranscript(
            ts=clock.iso(now), document=transcript.name, day=day.isoformat()
        ),
    )
    return stamp


def read(root, source):
    return [
        r
        for path in (root / "state" / source).glob("*.jsonl")
        for r in streams.read_day(path)
    ]


def test_interactions_document(temp_root, monkeypatch):
    """PRD interactions AC-3, AC-11, AC-13, AC-16; no LLM and no mains power
    needed (owner decision, 2026-11-25)."""
    monkeypatch.setenv("HOME", str(temp_root / "home"))
    monkeypatch.setenv("TZ", "Europe/Stockholm")
    monkeypatch.setattr(power, "on_mains", lambda: False)
    stamp = seed(temp_root)
    result = CliRunner().invoke(app, ["run", "interactions", "--once"])
    assert result.exit_code == 0, result.output
    docs = list((temp_root / "state/documents/interactions").glob("*.md"))
    assert len(docs) == 1
    first = clock.parse_iso(stamp()).astimezone(ZoneInfo("Europe/Stockholm"))
    assert docs[0].name == f"{first:%Y-%m-%d-%H%M}-test-host-weekly-sync.md"
    content = docs[0].read_text()
    meta = parse_front_matter(content)
    assert meta.host == "test-host"
    assert meta.meeting and meta.meeting.code == "abc-defg-hij"
    assert meta.timezone == "Europe/Stockholm"
    assert meta.start.endswith("+01:00")
    assert meta.participants == ["Alice", "Bob", "Oscar", "Oscar Tile"]
    assert meta.title == "Weekly sync"
    assert "\n# Weekly sync\n\n## Transcript\n" in content
    assert "## Summary" not in content
    assert "**Alice:** Partitionerna orsakar luckor." in content
    assert "**Bob:** Jag skriver planen i morgon." in content
    assert "**Oscar:** Vi behöver flytta databasen" in content
    assert "📝 **Note:** check the CDC lag numbers" in content
    assert "PRIVATE DICTATION" not in content
    record = InteractionRecord.model_validate(read(temp_root, "interactions")[0])
    finished = FinishedInteraction.model_validate(
        read(temp_root, "finished/interactions")[0]
    )
    assert record.outcome == "ok" and record.lines == 5
    assert finished.document == docs[0].name == record.document
    assert finished.id == meta.id == record.id
    # A second drain must not change the document or add records.
    result = CliRunner().invoke(app, ["run", "interactions", "--once"])
    assert result.exit_code == 0, result.output
    assert len(read(temp_root, "interactions")) == 1
    assert len(read(temp_root, "finished/interactions")) == 1
    assert docs[0].read_text() == content
    assert (
        temp_root / "state/documents/transcripts/fixture.md"
    ).read_text() == "Fixture daily transcript.\n"
