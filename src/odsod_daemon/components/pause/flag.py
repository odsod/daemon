"""Atomic pause flag access, shared by control components."""

from pathlib import Path

from odsod_daemon.components.pause.contract import PausedFlag
from odsod_daemon.lib import documents


def read(run: Path) -> PausedFlag | None:
    path = run / "paused"
    if not path.exists():
        return None
    return PausedFlag.model_validate(documents.read_json(path))


def write(run: Path, since: str) -> None:
    documents.write_json(run / "paused", PausedFlag(since=since).model_dump())


def remove(run: Path) -> None:
    documents.remove(run / "paused")
