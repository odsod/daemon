"""Speaking-class discovery. Pure: snapshots in, one class out.

A candidate is the shortest CSS class that changed between two snapshots. It
is confirmed after a number of on/off toggles, so a class that changes for
layout never wins.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from odsod_daemon.components.signals.platforms.base import SnapshotTile


@dataclass(frozen=True)
class DiscoveryResult:
    tiles: tuple[SnapshotTile, ...]
    confirmed: str | None = None


class Discovery:
    def __init__(self, toggles_required: int = 3) -> None:
        self._required = toggles_required
        self._prev: dict[str, frozenset[str]] | None = None
        self._candidate: str | None = None
        self._toggles = 0
        self._present = False

    def observe(self, tiles: Sequence[SnapshotTile]) -> DiscoveryResult:
        current = {tile.name: tile.classes for tile in tiles}
        result = DiscoveryResult(tuple(tiles))
        if self._prev is None:
            self._prev = current
            return result

        changed = _changed(self._prev, current)
        self._prev = current
        if not changed:
            return result

        candidate = min(changed, key=lambda name: (len(name), name))
        if candidate != self._candidate:
            self._candidate = candidate
            self._toggles = 0
            self._present = _present(current, candidate)
            return result

        present = _present(current, candidate)
        if present != self._present:
            self._toggles += 1
            self._present = present
        if self._toggles < self._required:
            return result

        confirmed = candidate
        self._candidate = None
        self._toggles = 0
        return DiscoveryResult(result.tiles, confirmed)


def _changed(
    before: dict[str, frozenset[str]],
    after: dict[str, frozenset[str]],
) -> set[str]:
    changed: set[str] = set()
    for name in before.keys() | after.keys():
        changed |= before.get(name, frozenset()) ^ after.get(name, frozenset())
    return changed


def _present(snapshot: dict[str, frozenset[str]], name: str) -> bool:
    return any(name in classes for classes in snapshot.values())
