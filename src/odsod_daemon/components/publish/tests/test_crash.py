"""A crash after the rename and before the record copies at most once more."""

from __future__ import annotations

import pytest

from odsod_daemon.components.publish import deliver
from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_crash_after_rename_copies_at_most_once_more(
    temp_root, fake_clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    source = finish(temp_root, "day.md", "transcripts", now)
    settings = publishing(temp_root, [target("vault", directory)])

    # Steps 1 to 3 complete; the process dies before step 4.
    deliver.copy(source, directory)
    assert (directory / source.name).exists()
    assert deliveries(temp_root, "vault") == []

    copies = []
    real = deliver.copy

    def count(*args, **kwargs):
        copies.append(args[0].name)
        return real(*args, **kwargs)

    monkeypatch.setattr(deliver, "copy", count)
    scan(publisher(settings, now), now)

    assert copies == [source.name]
    assert sorted(path.name for path in directory.iterdir()) == [source.name]
    assert len(deliveries(temp_root, "vault")) == 1
