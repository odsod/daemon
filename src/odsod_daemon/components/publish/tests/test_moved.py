"""A moved or deleted copy is never written again, also after a restart."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_deleted_copy_is_not_written_again(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    source = finish(temp_root, "2026-11-23-host.md", "transcripts", now)
    settings = publishing(temp_root, [target("vault", directory)])

    scan(publisher(settings, now), now)
    assert (directory / source.name).exists()
    (directory / source.name).unlink()

    fake_clock.advance(minutes=1)
    scan(publisher(settings, fake_clock.now), fake_clock.now)

    assert not (directory / source.name).exists()
    assert len(deliveries(temp_root, "vault")) == 1
