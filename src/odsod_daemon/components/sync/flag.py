"""The sync pause flag. It stays across reboots, so a host on mobile data
does not sync after a restart (ADR-0024)."""

from __future__ import annotations

from pathlib import Path

from odsod_daemon.components.sync.contract import SyncPaused
from odsod_daemon.lib import documents

NAME = "sync-paused"


def read(state: Path) -> SyncPaused | None:
    path = state / NAME
    if not path.exists():
        return None
    return SyncPaused.model_validate(documents.read_json(path))


def write(state: Path, since: str) -> None:
    documents.write_json(state / NAME, SyncPaused(since=since).model_dump())


def remove(state: Path) -> None:
    documents.remove(state / NAME)
