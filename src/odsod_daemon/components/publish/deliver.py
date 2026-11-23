"""Copy one document into one target directory.

The rename into the target is the commit point. The target is never read:
the copy is written to a temp name, synced, and renamed over any old copy.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import stat
from pathlib import Path

from odsod_daemon.lib import documents

CHUNK = 65536

REASONS = {
    errno.ENOENT: "missing",
    errno.ENOTDIR: "missing",
    errno.ENOSPC: "full",
    errno.EDQUOT: "full",
    errno.EACCES: "permission denied",
    errno.EPERM: "permission denied",
    errno.EROFS: "read-only",
}


class TargetUnavailable(Exception):
    """The target directory cannot take a copy right now."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DocumentGone(Exception):
    """The source document vanished before the copy started."""


def reason(error: OSError) -> str:
    return REASONS.get(error.errno or 0, error.strerror or str(error))


def check(directory: Path) -> None:
    """Refuse a target that is absent or not a directory. Never create it."""
    try:
        info = os.stat(directory)
    except OSError as error:
        raise TargetUnavailable(reason(error)) from error
    if not stat.S_ISDIR(info.st_mode):
        raise TargetUnavailable("not a directory")


def writable(directory: Path) -> bool:
    """True if the target is a directory that this process can write into."""
    try:
        check(directory)
    except TargetUnavailable:
        return False
    return os.access(directory, os.W_OK | os.X_OK)


def _sync(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy(source: Path, directory: Path) -> tuple[int, str]:
    """Copy ``source`` into ``directory``. Return its size and SHA-256."""
    check(directory)
    destination = directory / source.name
    temp = documents.temp_name(destination)
    size = 0
    digest = hashlib.sha256()
    try:
        origin = source.open("rb")
    except FileNotFoundError as error:
        raise DocumentGone(str(source)) from error
    try:
        with origin, temp.open("wb") as copy_file:
            while chunk := origin.read(CHUNK):
                copy_file.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            copy_file.flush()
            os.fsync(copy_file.fileno())
        os.replace(temp, destination)
        _sync(directory)
    except OSError as error:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        raise TargetUnavailable(reason(error)) from error
    return size, digest.hexdigest()
