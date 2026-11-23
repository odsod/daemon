"""A document is delivered only after its finished record exists."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    document,
    finished,
    publisher,
    publishing,
    scan,
    target,
)


def test_document_without_finished_record_is_not_delivered(
    temp_root, fake_clock
) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    settings = publishing(temp_root, [target("vault", directory)])
    name = "2026-11-23-host.md"
    document(temp_root, name, "transcripts", "# day\n")
    pub = publisher(settings, fake_clock.now)

    scan(pub, fake_clock.now)
    assert not (directory / name).exists()
    assert deliveries(temp_root, "vault") == []

    finished(temp_root, name, "transcripts", fake_clock.now)
    scan(pub, fake_clock.now)
    assert (directory / name).read_text() == "# day\n"
    assert len(deliveries(temp_root, "vault")) == 1
