from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from odsod_daemon.components.signals.discovery import Discovery
from odsod_daemon.components.signals.platforms.base import SnapshotTile

TESTDATA = Path(__file__).parent / "testdata" / "discovery"


def fixtures() -> Iterator[dict[str, Any]]:
    for path in sorted(TESTDATA.glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))


def snapshots(raw: list[Any]) -> list[list[SnapshotTile]]:
    result: list[list[SnapshotTile]] = []
    for snapshot in raw:
        tiles: list[SnapshotTile] = []
        for item in snapshot:
            assert isinstance(item, dict)
            tiles.append(
                SnapshotTile(
                    str(item["name"]),
                    frozenset(str(name) for name in item["classes"]),
                )
            )
        result.append(tiles)
    return result


def test_confirms_the_speaking_class_only() -> None:
    for fixture in fixtures():
        discovery = Discovery(toggles_required=3)
        confirmed: list[str] = []
        for snapshot in snapshots(fixture["snapshots"]):
            result = discovery.observe(snapshot)
            if result.confirmed is not None:
                confirmed.append(result.confirmed)
        assert confirmed == (
            [] if fixture["confirmed"] is None else [fixture["confirmed"]]
        )


def test_layout_class_never_confirms() -> None:
    fixture = json.loads((TESTDATA / "meet_layout.json").read_text(encoding="utf-8"))
    discovery = Discovery(toggles_required=3)
    for index, snapshot in enumerate(snapshots(fixture["snapshots"])):
        result = discovery.observe(snapshot)
        assert result.confirmed is None, index


def test_toggle_count_must_reach_the_requirement() -> None:
    discovery = Discovery(toggles_required=3)
    present = [SnapshotTile("Alice Smith", frozenset({"tile", "x"}))]
    absent = [SnapshotTile("Alice Smith", frozenset({"tile"}))]
    assert discovery.observe(absent).confirmed is None
    assert discovery.observe(present).confirmed is None
    assert discovery.observe(absent).confirmed is None
    assert discovery.observe(present).confirmed is None
    assert discovery.observe(absent).confirmed == "x"


def test_shortest_changed_class_wins() -> None:
    discovery = Discovery(toggles_required=1)
    base = [SnapshotTile("Alice", frozenset({"bb"}))]
    assert discovery.observe(base).confirmed is None
    assert (
        discovery.observe(
            [SnapshotTile("Alice", frozenset({"bb", "zzzzzz", "a", "ccc"}))]
        ).confirmed
        is None
    )
    assert discovery.observe(base).confirmed == "a"


def test_equal_length_classes_are_deterministic() -> None:
    discovery = Discovery(toggles_required=1)
    empty = [SnapshotTile("Alice", frozenset())]
    assert discovery.observe(empty).confirmed is None
    assert (
        discovery.observe([SnapshotTile("Alice", frozenset({"bb", "aa"}))]).confirmed
        is None
    )
    assert discovery.observe(empty).confirmed == "aa"


def test_a_vanished_tile_counts_as_a_change() -> None:
    discovery = Discovery(toggles_required=1)
    tiles = [
        SnapshotTile("Alice", frozenset({"tile"})),
        SnapshotTile("Bob", frozenset({"tile", "gone"})),
    ]
    alice = [SnapshotTile("Alice", frozenset({"tile"}))]
    assert discovery.observe(tiles).confirmed is None
    assert discovery.observe(alice).confirmed is None
    assert discovery.observe(tiles).confirmed == "gone"


def test_first_snapshot_has_no_speakers() -> None:
    discovery = Discovery()
    result = discovery.observe([SnapshotTile("Alice", frozenset({"x"}))])
    assert result.confirmed is None
    assert result.tiles == (SnapshotTile("Alice", frozenset({"x"})),)


def test_no_change_keeps_discovery_open() -> None:
    discovery = Discovery()
    tiles = [SnapshotTile("Alice", frozenset({"tile"}))]
    assert discovery.observe(tiles).confirmed is None
    assert discovery.observe(tiles).confirmed is None


def test_tiles_are_returned_in_page_order() -> None:
    discovery = Discovery()
    tiles = [
        SnapshotTile("Bob", frozenset({"tile"})),
        SnapshotTile("Alice", frozenset({"tile"})),
    ]
    assert [tile.name for tile in discovery.observe(tiles).tiles] == ["Bob", "Alice"]


@pytest.mark.parametrize("required", [1, 3, 5])
def test_requirement_comes_from_config(required: int) -> None:
    discovery = Discovery(toggles_required=required)
    present = [SnapshotTile("Alice", frozenset({"x"}))]
    absent = [SnapshotTile("Alice", frozenset())]
    discovery.observe(absent)
    confirmed = None
    for _ in range(required + 1):
        confirmed = confirmed or discovery.observe(present).confirmed
        confirmed = confirmed or discovery.observe(absent).confirmed
    assert confirmed == "x"
