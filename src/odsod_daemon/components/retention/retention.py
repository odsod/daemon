"""Pure retention: hour files older than the period are deleted."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

HOUR_FORMAT = "%Y%m%dT%HZ"


def hour_start(path: Path) -> datetime | None:
    """The UTC hour start in a file name, or None when it does not parse."""
    try:
        return datetime.strptime(path.stem, HOUR_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def is_expired(path: Path, now: datetime, retention_days: int) -> bool:
    """True when the file's first second is older than the period."""
    start = hour_start(path)
    if start is None:
        return False
    return now - start >= timedelta(days=retention_days)


def files_to_delete(
    files: Iterable[Path], now: datetime, retention_days: int
) -> list[Path]:
    return [path for path in files if is_expired(path, now, retention_days)]


def audio_files(state_root: Path) -> list[Path]:
    """Every ``*.pcm`` under ``state/audio/*/``, with no symlinks followed."""
    root = state_root / "audio"
    if not root.is_dir() or root.is_symlink():
        return []
    files: list[Path] = []
    for directory in sorted(root.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.pcm")):
            if not path.is_symlink() and path.is_file():
                files.append(path)
    return files
