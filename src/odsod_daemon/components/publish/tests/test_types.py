"""A target gets only the document types it names."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_target_gets_only_its_types(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    transcript = finish(temp_root, "day.md", "transcripts", now)
    interaction = finish(temp_root, "meeting.md", "interactions", now)
    settings = publishing(
        temp_root, [target("meetings", directory, types=["interactions"])]
    )

    scan(publisher(settings, now), now)

    assert not (directory / transcript.name).exists()
    assert (directory / interaction.name).exists()
    assert [record["document"] for record in deliveries(temp_root, "meetings")] == [
        interaction.name
    ]
