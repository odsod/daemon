"""Publishing never opens a target file for reading."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_publish_never_reads_a_target_file(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    source = finish(temp_root, "day.md", "transcripts", now, "from the daemon\n")
    existing = directory / source.name
    existing.write_text("from the target\n")
    existing.chmod(0o000)
    settings = publishing(temp_root, [target("vault", directory)])

    try:
        scan(publisher(settings, now), now)
    finally:
        existing.chmod(0o600)

    assert existing.read_text() == "from the daemon\n"
    assert len(deliveries(temp_root, "vault")) == 1
    assert not list(directory.glob(".*.tmp"))
