"""Directory change events from inotify, read on the asyncio event loop.

No thread and no polling: the loop wakes only when the kernel reports a
change, so an idle watcher costs nothing.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
from pathlib import Path

_libc = ctypes.CDLL(None, use_errno=True)

IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE


class DirectoryWatch:
    """Set ``changed`` when a file in one directory is created or written."""

    def __init__(self, directory: Path) -> None:
        self.changed = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        fd = _libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if fd < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        if _libc.inotify_add_watch(fd, os.fsencode(directory), MASK) < 0:
            error = ctypes.get_errno()
            os.close(fd)
            raise OSError(error, os.strerror(error), str(directory))
        self._fd = fd
        self._loop.add_reader(fd, self._read)

    def _read(self) -> None:
        try:
            while os.read(self._fd, 65536):
                pass
        except BlockingIOError:
            pass
        self.changed.set()

    def close(self) -> None:
        if self._fd < 0:
            return
        self._loop.remove_reader(self._fd)
        os.close(self._fd)
        self._fd = -1
