"""Table tests for the pure pending rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.publish.pending import Finished, pending

SINCE = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def item(name: str, type_: str, seconds: float) -> Finished:
    return Finished(
        document=name,
        type=type_,  # type: ignore[arg-type]
        at=SINCE + timedelta(seconds=seconds),
        path=Path("/nope") / name,
    )


@pytest.mark.parametrize(
    ("finished", "delivered", "types", "expected"),
    [
        ([item("a", "transcripts", 0)], [], ["transcripts"], ["a"]),
        ([item("a", "transcripts", 0)], ["a"], ["transcripts"], []),
        ([item("a", "transcripts", -1)], [], ["transcripts"], []),
        ([item("a", "interactions", 0)], [], ["transcripts"], []),
        (
            [item("a", "transcripts", 5), item("b", "transcripts", 1)],
            [],
            ["transcripts", "interactions"],
            ["b", "a"],
        ),
        (
            [item("a", "transcripts", 5), item("a", "transcripts", 1)],
            [],
            ["transcripts"],
            ["a"],
        ),
    ],
)
def test_pending(finished, delivered, types, expected) -> None:
    result = pending(finished, delivered, since=SINCE, types=types)
    assert [entry.document for entry in result] == expected


def test_pending_keeps_the_oldest_record_of_a_document() -> None:
    older = item("a", "transcripts", 1)
    newer = item("a", "transcripts", 2)
    assert pending([newer, older], [], since=SINCE, types=["transcripts"]) == [older]
