"""One target's success clears its fault and never the other's."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    faults,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_only_the_returning_target_fault_clears(temp_root, fake_clock) -> None:
    first, second = temp_root / "first", temp_root / "second"
    now = fake_clock.now
    source = finish(temp_root, "day.md", "transcripts", now)
    settings = publishing(
        temp_root,
        [target("first", first), target("second", second)],
        retry_s=30,
    )
    pub = publisher(settings, now)

    scan(pub, now)
    assert {fault["key"] for fault in faults(temp_root)} == {"first", "second"}

    first.mkdir()
    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)
    assert [fault["key"] for fault in faults(temp_root)] == ["second"]
    assert (first / source.name).exists()
    assert not second.exists()

    second.mkdir()
    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)
    assert faults(temp_root) == []
    assert (second / source.name).exists()
    assert len(deliveries(temp_root, "first")) == 1
    assert len(deliveries(temp_root, "second")) == 1
