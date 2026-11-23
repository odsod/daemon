from __future__ import annotations

import pytest

from odsod_daemon.lib import textmatch


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("", "", 0.0),
        ("hej", "", 0.0),
        ("Hej, hur mår du?", "hej hur mår du", 1.0),
        ("the migration plan", "the migration plan today", 1.0),
        ("the migration plan", "migration plan", 0.0),
        ("Yes", "yes I think so", 0.0),
        ("Okay.", "okay", 0.0),
        ("one two three four", "one two three five", 0.75),
        ("one two three", "four five six", 0.0),
        ("Hello big world", "hello there big world", 1.0),
        ("Hello world", "hello there world", 0.0),
        ("a b c d", "a b x y", 0.5),
    ],
)
def test_overlap(left: str, right: str, expected: float) -> None:
    assert textmatch.overlap(left, right) == pytest.approx(expected)


def test_overlap_is_symmetric() -> None:
    assert textmatch.overlap("a b c", "a b d") == textmatch.overlap("a b d", "a b c")


def test_normalize_strips_punctuation_and_case() -> None:
    assert textmatch.normalize("  Hej,   VÄRLDEN!  ") == "hej världen"
