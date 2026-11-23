"""Hour files: pwrite at a time offset, split at the hour boundary.

A block that crosses the hour is split over two files. The file offset of a
time is ``(time - hour start) * 32,000`` bytes, aligned to a sample. The
writer never moves the file size back, so audio time never runs backward.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from odsod_daemon.lib import audio


class Writer:
    """Write one channel to its hourly files."""

    def __init__(self, state_root: Path, channel: str) -> None:
        self.state_root = state_root
        self.channel = channel
        self._ready: set[Path] = set()

    def write(self, start: float, data: bytes) -> None:
        moment = datetime.fromtimestamp(start, UTC)
        cursor = 0
        while cursor < len(data):
            to_hour_end = (audio.hour_end(moment) - moment).total_seconds()
            room = int(to_hour_end * audio.BYTES_PER_SECOND)
            take = min(len(data) - cursor, max(2, room))
            take -= take % 2
            self._piece(moment, data[cursor : cursor + take])
            cursor += take
            moment = audio.hour_end(moment)

    def end(self) -> float | None:
        """Wall time of the end of the newest audio, or None."""
        covered = audio.covered_until(self.state_root, self.channel)
        return None if covered is None else covered.timestamp()

    def _piece(self, moment: datetime, data: bytes) -> None:
        path = audio.hour_file(self.state_root, self.channel, moment)
        self._secure(path.parent)
        offset = _offset(moment)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            size = os.fstat(fd).st_size
            if offset + len(data) <= size:
                return
            if offset < size:
                data = data[size - offset :]
                offset = size
            _pwrite_all(fd, data, offset)
        finally:
            os.close(fd)

    def _secure(self, directory: Path) -> None:
        if directory in self._ready:
            return
        for path in (self.state_root / "audio", directory):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)
        self._ready.add(directory)


def _offset(moment: datetime) -> int:
    """Byte offset of a time inside its hour, aligned to a sample."""
    seconds = (moment - audio.hour_start(moment)).total_seconds()
    offset = int(seconds * audio.BYTES_PER_SECOND)
    return offset - offset % 2


def _pwrite_all(fd: int, data: bytes, offset: int) -> None:
    while data:
        written = os.pwrite(fd, data, offset)
        if written <= 0:
            raise OSError("short write to the audio buffer")
        data = data[written:]
        offset += written
