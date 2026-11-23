"""Interaction documents through file contracts and the CLI."""

import copy
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
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
from odsod_daemon.lib import clock, inference, power, streams

DATA = Path(inference.__file__).parent / "testdata"


def seed(root: Path, server: inference.ReplayServer):
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
                        "llama_url": server.url + inference.LLAMA_PATH,
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
    # Dictation is complete for the gate, but must never enter a summary.
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
    monkeypatch.setenv("HOME", str(temp_root / "home"))
    monkeypatch.setenv("TZ", "Europe/Stockholm")
    monkeypatch.setattr(power, "on_mains", lambda: True)
    pair = json.loads((DATA / "llama-summary.json").read_text())
    server = inference.ReplayServer([pair])
    try:
        seed(temp_root, server)
        result = CliRunner().invoke(app, ["run", "interactions", "--once"])
        assert result.exit_code == 0, result.output
        docs = list((temp_root / "state/documents/interactions").glob("*.md"))
        assert len(docs) == 1
        content = docs[0].read_text()
        meta = parse_front_matter(content)
        assert meta.host == "test-host"
        assert meta.meeting and meta.meeting.code == "abc-defg-hij"
        assert meta.timezone == "Europe/Stockholm"
        assert meta.start.endswith("+01:00")
        assert meta.participants == ["Alice", "Bob", "Oscar", "Oscar Tile"]
        assert len(meta.title.split()) <= 8
        assert "**Alice:** Partitionerna orsakar luckor." in content
        assert "**Bob:** Jag skriver planen i morgon." in content
        assert "**Oscar:** Vi behöver flytta databasen" in content
        assert "📝 **Note:** check the CDC lag numbers" in content
        assert "PRIVATE DICTATION" not in content
        body = json.loads(server.requests[0]["body"])
        assert "PRIVATE DICTATION" not in body["messages"][1]["content"]
        assert "Partitionerna orsakar luckor." in body["messages"][1]["content"]
        record = InteractionRecord.model_validate(read(temp_root, "interactions")[0])
        finished = FinishedInteraction.model_validate(
            read(temp_root, "finished/interactions")[0]
        )
        assert record.outcome == "ok" and record.lines == 5
        assert finished.document == docs[0].name == record.document
        assert finished.id == meta.id == record.id
        # A second drain must not request another summary or change the document.
        result = CliRunner().invoke(app, ["run", "interactions", "--once"])
        assert result.exit_code == 0, result.output
        assert len(server.requests) == 1
        assert len(read(temp_root, "interactions")) == 1
        assert len(read(temp_root, "finished/interactions")) == 1
        assert docs[0].read_text() == content
        assert (
            temp_root / "state/documents/transcripts/fixture.md"
        ).read_text() == "Fixture daily transcript.\n"
    finally:
        server.close()


@pytest.mark.parametrize("error", ["bad-json", "schema", "http"])
def test_interactions_failed_replies(temp_root, monkeypatch, error):
    monkeypatch.setenv("HOME", str(temp_root / "home"))
    monkeypatch.setattr(power, "on_mains", lambda: True)
    pair = copy.deepcopy(json.loads((DATA / "llama-summary.json").read_text()))
    if error == "http":
        pair["response"]["status"] = 400
    else:
        pair["response"]["json"]["choices"][0]["message"]["content"] = (
            "bad" if error == "bad-json" else "{}"
        )
    server = inference.ReplayServer([pair])
    try:
        seed(temp_root, server)
        path = temp_root / "config/config.json"
        conf = json.loads(path.read_text())
        conf["interactions"]["max_attempts"] = 1
        path.write_text(json.dumps(conf))
        result = CliRunner().invoke(app, ["run", "interactions", "--once"])
        assert result.exit_code == 0, result.output
        assert read(temp_root, "interactions")[0]["outcome"] == "failed"
        assert not read(temp_root, "finished/interactions")
    finally:
        server.close()
