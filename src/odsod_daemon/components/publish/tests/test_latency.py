"""A new finished document reaches a present target within a minute."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_new_document_reaches_a_target_within_a_minute(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    settings = publishing(temp_root, [target("vault", directory)])
    started = fake_clock.now
    pub = publisher(settings, started)

    fake_clock.advance(seconds=10)
    finish(temp_root, "2026-11-23-host.md", "transcripts", fake_clock.now)
    scan(pub, fake_clock.now)

    assert (directory / "2026-11-23-host.md").exists()
    assert (fake_clock.now - started).total_seconds() <= 60
