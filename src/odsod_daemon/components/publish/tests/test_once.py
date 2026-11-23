"""``run(..., once=True)`` drains pending work and returns."""

from __future__ import annotations

from odsod_daemon.components.publish.service import run
from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    faults,
    finish,
    publishing,
    target,
)


async def test_once_delivers_every_pending_document(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    first = finish(temp_root, "first.md", "transcripts", now)
    second = finish(temp_root, "second.md", "interactions", now)
    settings = publishing(temp_root, [target("vault", directory)])

    await run(settings, once=True)

    assert (directory / first.name).exists()
    assert (directory / second.name).exists()
    assert len(deliveries(temp_root, "vault")) == 2
    assert faults(temp_root) == []


async def test_once_with_no_targets_does_nothing(temp_root, fake_clock) -> None:
    settings = publishing(temp_root, [])

    await run(settings, once=True)

    assert faults(temp_root) == []
