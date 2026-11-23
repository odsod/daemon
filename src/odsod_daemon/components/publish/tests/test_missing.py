"""A missing or full target faults, then clears on the next success."""

from __future__ import annotations

import errno

import pytest

from odsod_daemon.components.publish import deliver
from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    faults,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_missing_target_faults_then_delivers_on_return(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    now = fake_clock.now
    source = finish(temp_root, "2026-11-23-host.md", "transcripts", now)
    settings = publishing(temp_root, [target("vault", directory)], retry_s=30)
    pub = publisher(settings, now)

    scan(pub, now)

    waiting = faults(temp_root)
    assert len(waiting) == 1
    assert waiting[0]["code"] == "target-missing"
    assert waiting[0]["key"] == "vault"
    assert waiting[0]["fix"] is None
    assert "missing" in waiting[0]["message"]
    assert (fake_clock.now - now).total_seconds() <= 60
    assert not (directory / source.name).exists()

    directory.mkdir()
    fake_clock.advance(seconds=10)
    scan(pub, fake_clock.now)
    assert not (directory / source.name).exists()

    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)
    assert (directory / source.name).read_text() == source.read_text()
    assert faults(temp_root) == []
    assert len(deliveries(temp_root, "vault")) == 1


def test_full_target_maps_to_the_target_fault(
    temp_root, fake_clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    source = finish(temp_root, "day.md", "transcripts", fake_clock.now)

    def full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(deliver.os, "replace", full)
    with pytest.raises(deliver.TargetUnavailable) as error:
        deliver.copy(source, directory)

    assert error.value.reason == "full"
    assert list(directory.glob(".*.tmp")) == []


def test_full_target_shows_its_reason(
    temp_root, fake_clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    finish(temp_root, "day.md", "transcripts", now)
    settings = publishing(temp_root, [target("vault", directory)])

    def full(*args, **kwargs):
        raise deliver.TargetUnavailable("full")

    monkeypatch.setattr(deliver, "copy", full)
    scan(publisher(settings, now), now)

    assert "`full`" in faults(temp_root)[0]["message"]


def test_fault_clears_when_target_returns_with_nothing_pending(
    temp_root, fake_clock
) -> None:
    directory = temp_root / "target"
    now = fake_clock.now
    source = finish(temp_root, "day.md", "transcripts", now)
    settings = publishing(temp_root, [target("vault", directory)], retry_s=30)
    pub = publisher(settings, now)
    scan(pub, now)
    assert [fault["key"] for fault in faults(temp_root)] == ["vault"]

    source.unlink()
    directory.mkdir(mode=0o500)
    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)
    assert [fault["key"] for fault in faults(temp_root)] == ["vault"]

    directory.chmod(0o700)
    fake_clock.advance(seconds=30)
    scan(pub, fake_clock.now)
    assert faults(temp_root) == []
    assert deliveries(temp_root, "vault") == []
