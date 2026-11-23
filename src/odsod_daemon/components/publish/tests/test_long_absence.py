"""A target absent for 30 days still gets every document on return."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_long_absence_delivers_every_document(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    now = fake_clock.now
    settings = publishing(temp_root, [target("vault", directory)], retry_s=30)
    pub = publisher(settings, now)
    names = []

    for index in range(30):
        fake_clock.advance(days=1)
        name = f"2026-11-{index + 1:02d}-host.md"
        names.append(name)
        finish(temp_root, name, "transcripts", fake_clock.now, f"{index}\n")
        scan(pub, fake_clock.now)
        assert not directory.exists()

    directory.mkdir()
    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)

    assert sorted(path.name for path in directory.iterdir()) == sorted(names)
    assert len(deliveries(temp_root, "vault")) == len(names)
