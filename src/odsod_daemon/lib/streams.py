"""Append-only JSONL streams.

A writer appends one whole line with one ``write`` call. A reader uses only
lines that end in a newline. ``follow`` wakes on inotify and also scans on a
timer, so a missed event never loses a record.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import OrderedDict
from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from odsod_daemon.lib import inotify

DEFAULT_SCAN_S = 2.0


def day_path(directory: Path, day: date) -> Path:
    return directory / f"{day.isoformat()}.jsonl"


def append(path: Path, record: Mapping[str, Any]) -> None:
    """Append one record as one line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


# Day files are append-only, so read_day keeps what it parsed and reads only
# the new bytes. Services re-read whole days about 30 times a second.
_CACHE_SIZE = 64
_cache: OrderedDict[Path, tuple[int, int, list[dict[str, Any]]]] = OrderedDict()


def read_day(path: Path) -> list[dict[str, Any]]:
    """Read the complete lines of a day file."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        _cache.pop(path, None)
        return []
    inode, offset, records = _cache.pop(path, (stat.st_ino, 0, []))
    if inode != stat.st_ino or stat.st_size < offset:
        offset, records = 0, []
    if stat.st_size > offset:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(stat.st_size - offset)
        data = data[: data.rfind(b"\n") + 1]
        offset += len(data)
        for raw in data.splitlines():
            if raw.strip():
                records.append(json.loads(raw))
    _cache[path] = (stat.st_ino, offset, records)
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    # Callers may change what they get: give each a copy of every record.
    return [dict(record) for record in records]


def read_days(directory: Path, start: date, end: date) -> list[dict[str, Any]]:
    """Read complete records from every day file in an inclusive range."""
    records: list[dict[str, Any]] = []
    day = start
    while day <= end:
        records.extend(read_day(day_path(directory, day)))
        day += timedelta(days=1)
    return records


def _decode_lines(buffer: bytes) -> tuple[list[dict[str, Any]], bytes]:
    records: list[dict[str, Any]] = []
    while True:
        newline = buffer.find(b"\n")
        if newline < 0:
            return records, buffer
        raw = buffer[:newline]
        buffer = buffer[newline + 1 :]
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)


class _Tail:
    def __init__(self, path: Path, *, start_at_end: bool) -> None:
        self.path = path
        self.offset = _size(path) if start_at_end else 0
        self.buffer = b""

    def drain(self) -> list[dict[str, Any]]:
        size = _size(self.path)
        if size < self.offset:
            self.offset = 0
            self.buffer = b""
        if size == self.offset:
            return []
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
        self.offset += len(chunk)
        records, self.buffer = _decode_lines(self.buffer + chunk)
        return records


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


async def follow(
    path: Path,
    *,
    start_at_end: bool = True,
    scan_s: float = DEFAULT_SCAN_S,
) -> AsyncIterator[dict[str, Any]]:
    """Yield complete records as they are appended to a stream file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tail = _Tail(path, start_at_end=start_at_end)
    watch = inotify.DirectoryWatch(path.parent)
    try:
        while True:
            # Clear before the drain: a write during the drain wakes the wait.
            watch.changed.clear()
            for record in tail.drain():
                yield record
            try:
                await asyncio.wait_for(watch.changed.wait(), timeout=scan_s)
            except TimeoutError:
                continue
    finally:
        watch.close()


def append_all(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    for record in records:
        append(path, record)
