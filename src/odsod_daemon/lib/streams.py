"""Append-only JSONL streams.

A writer appends one whole line with one ``write`` call. A reader uses only
lines that end in a newline. ``follow`` wakes on inotify and also scans on a
timer, so a missed event never loses a record.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import watchfiles

DEFAULT_DEBOUNCE_MS = 20
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


def read_day(path: Path) -> list[dict[str, Any]]:
    """Read the complete lines of a day file."""
    if not path.exists():
        return []
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
    records: list[dict[str, Any]] = []
    for raw in data.splitlines():
        if raw.strip():
            records.append(json.loads(raw))
    return records


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
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    step_ms: int = 10,
    scan_s: float = DEFAULT_SCAN_S,
) -> AsyncIterator[dict[str, Any]]:
    """Yield complete records as they are appended to a stream file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tail = _Tail(path, start_at_end=start_at_end)
    changes: asyncio.Queue[None] = asyncio.Queue(maxsize=1)

    async def watch() -> None:
        async for _ in watchfiles.awatch(
            path.parent, debounce=debounce_ms, step=step_ms
        ):
            if changes.full():
                changes.get_nowait()
            changes.put_nowait(None)

    watcher = asyncio.create_task(watch())
    try:
        while True:
            for record in tail.drain():
                yield record
            try:
                await asyncio.wait_for(changes.get(), timeout=scan_s)
            except TimeoutError:
                continue
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


def append_all(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    for record in records:
        append(path, record)
