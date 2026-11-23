"""Each finished document reaches each target that wants it."""

from __future__ import annotations

import hashlib

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_each_target_gets_each_finished_document(temp_root, fake_clock) -> None:
    first, second = temp_root / "first", temp_root / "second"
    first.mkdir()
    second.mkdir()
    now = fake_clock.now
    transcript = finish(temp_root, "2026-11-23-host.md", "transcripts", now, "# day\n")
    interaction = finish(
        temp_root, "interaction-1.md", "interactions", now, "# meeting\n"
    )
    settings = publishing(
        temp_root,
        [target("first", first), target("second", second)],
    )

    pub = publisher(settings, now)
    scan(pub, now)

    for name, directory in (("first", first), ("second", second)):
        assert (directory / transcript.name).read_text() == "# day\n"
        assert (directory / interaction.name).read_text() == "# meeting\n"
        records = deliveries(temp_root, name)
        assert [record["document"] for record in records] == [
            transcript.name,
            interaction.name,
        ]
        assert [record["type"] for record in records] == [
            "transcripts",
            "interactions",
        ]
        assert [record["target"] for record in records] == [name, name]
        for record, source in zip(records, (transcript, interaction), strict=True):
            data = source.read_bytes()
            assert record["bytes"] == len(data)
            assert record["sha256"] == hashlib.sha256(data).hexdigest()


def test_each_target_stream_starts_with_since(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    settings = publishing(temp_root, [target("vault", directory)])

    publisher(settings, fake_clock.now)

    first = deliveries(temp_root, "vault")
    assert first == []
    stream = list((temp_root / "state/published/vault").glob("*.jsonl"))
    assert len(stream) == 1
    lines = stream[0].read_text().splitlines()
    assert len(lines) == 1
    assert '"kind":"start"' in lines[0]
    assert '"since":"2026-11-23T12:00:00.000Z"' in lines[0]
