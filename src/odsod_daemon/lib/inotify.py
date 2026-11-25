"""Directory change events from inotify, read on the asyncio event loop.

No thread and no polling: the loop wakes only when the kernel reports a
change, so an idle watcher costs nothing.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import struct
from pathlib import Path

_libc = ctypes.CDLL(None, use_errno=True)

IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE
IN_IGNORED = 0x00008000
EVENT = struct.Struct("iIII")


def _check(result: int, *detail: str) -> int:
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), *detail)
    return result


class _Instance:
    """One inotify instance per event loop. The kernel allows 256 per user,
    so watches share it: one kernel watch per directory."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.fd = _check(_libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC))
        self.watches: dict[int, set[DirectoryWatch]] = {}
        loop.add_reader(self.fd, self._read)

    def add(self, watch: DirectoryWatch, directory: Path) -> int:
        wd = _check(
            _libc.inotify_add_watch(self.fd, os.fsencode(directory), MASK),
            str(directory),
        )
        self.watches.setdefault(wd, set()).add(watch)
        return wd

    def remove(self, watch: DirectoryWatch, wd: int) -> None:
        subscribers = self.watches.get(wd)
        if subscribers is not None:
            subscribers.discard(watch)
            if not subscribers:
                del self.watches[wd]
                _libc.inotify_rm_watch(self.fd, wd)
        if not self.watches:
            self.loop.remove_reader(self.fd)
            os.close(self.fd)
            del _instances[self.loop]

    def _read(self) -> None:
        woken: set[int] = set()
        overflow = False
        try:
            while data := os.read(self.fd, 65536):
                offset = 0
                while offset < len(data):
                    wd, mask, _, size = EVENT.unpack_from(data, offset)
                    offset += EVENT.size + size
                    if wd < 0:
                        overflow = True
                    else:
                        woken.add(wd)
                    if mask & IN_IGNORED:
                        # The directory is gone; its watch is void.
                        for watch in self.watches.pop(wd, set()):
                            watch.changed.set()
        except BlockingIOError:
            pass
        for wd, subscribers in self.watches.items():
            if overflow or wd in woken:
                for watch in subscribers:
                    watch.changed.set()


_instances: dict[asyncio.AbstractEventLoop, _Instance] = {}


class DirectoryWatch:
    """Set ``changed`` when a file in one directory is created or written."""

    def __init__(self, directory: Path) -> None:
        self.changed = asyncio.Event()
        loop = asyncio.get_running_loop()
        instance = _instances.get(loop)
        if instance is None:
            instance = _instances[loop] = _Instance(loop)
        try:
            self._wd = instance.add(self, directory)
        except OSError:
            if not instance.watches:
                instance.remove(self, -1)
            raise
        self._instance: _Instance | None = instance

    def close(self) -> None:
        if self._instance is None:
            return
        self._instance.remove(self, self._wd)
        self._instance = None
