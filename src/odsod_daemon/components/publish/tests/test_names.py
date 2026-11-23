"""Documents of two hosts keep different names in one target."""

from __future__ import annotations

from odsod_daemon.components.publish.tests.helpers import (
    deliveries,
    finish,
    publisher,
    publishing,
    scan,
    target,
)


def test_documents_of_two_hosts_do_not_clash(temp_root, fake_clock) -> None:
    directory = temp_root / "target"
    directory.mkdir()
    now = fake_clock.now
    first = finish(temp_root, "2026-11-23-host-a.md", "transcripts", now, "a\n")
    second = finish(temp_root, "2026-11-23-host-b.md", "transcripts", now, "b\n")
    settings = publishing(temp_root, [target("vault", directory)])

    scan(publisher(settings, now), now)

    assert first.name != second.name
    assert (directory / first.name).read_text() == "a\n"
    assert (directory / second.name).read_text() == "b\n"
    assert [record["document"] for record in deliveries(temp_root, "vault")] == [
        first.name,
        second.name,
    ]
