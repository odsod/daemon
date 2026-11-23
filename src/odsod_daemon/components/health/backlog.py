"""Track stream IDs with plain JSON and incremental file offsets."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from odsod_daemon.components.health.contract import Backlog
from odsod_daemon.lib import clock


class BacklogTracker:
    def __init__(self, state: Path, retention_days: int = 14):
        self.state = state
        self.retention_days = retention_days
        self.inputs: dict[str, tuple[str, str]] = {}
        self.outputs: set[str] = set()
        self.coverage: dict[str, str] = {}
        self._offsets: dict[Path, tuple[int, int]] = {}
        self._days: tuple[str, ...] = ()
        self.oldest_end: str | None = None

    def rebuild(self, now: datetime) -> None:
        self.inputs.clear()
        self.outputs.clear()
        self.coverage.clear()
        self._offsets.clear()
        self._days = self._window(now)
        self.update(now)

    def _window(self, now: datetime) -> tuple[str, ...]:
        return tuple(
            (now.date() - timedelta(days=i)).isoformat()
            for i in range(self.retention_days)
        )

    def update(self, now: datetime) -> None:
        days = self._window(now)
        if self._days and days != self._days:
            self.rebuild(now)
            return
        self._days = days
        for stream in (
            "utterances/ambient",
            "utterances/dictation",
            "text",
            "coverage",
        ):
            for day in days:
                path = self.state / stream / f"{day}.jsonl"
                for value in self._read_new(path):
                    if stream.startswith("utterances"):
                        self.inputs[value["id"]] = (value["start"], value["end"])
                    elif stream == "text":
                        self.outputs.add(value["input"])
                    elif value.get("kind") == "covered":
                        channel, end = value["channel"], value["end"]
                        self.coverage[channel] = max(
                            end, self.coverage.get(channel, end)
                        )

    def _read_new(self, path: Path) -> list[dict[str, Any]]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return []
        offset, inode = self._offsets.get(path, (0, stat.st_ino))
        if inode != stat.st_ino or stat.st_size < offset:
            raise ValueError(f"append-only stream replaced or truncated: {path}")
        if stat.st_size == offset:
            return []
        values = []
        with path.open("rb") as handle:
            handle.seek(offset)
            for line in handle:
                if not line.endswith(b"\n"):
                    break
                offset += len(line)
                if line.strip():
                    values.append(json.loads(line))
        self._offsets[path] = (offset, stat.st_ino)
        return values

    def report(
        self,
        now: datetime,
        newest: dict[str, str | None],
        warning_s: float,
        audio_starts: dict[str, str] | None = None,
    ) -> Backlog:
        pending = [
            value for key, value in self.inputs.items() if key not in self.outputs
        ]
        seconds = sum(
            (clock.parse_iso(end) - clock.parse_iso(start)).total_seconds()
            for start, end in pending
        )
        starts = [start for start, _ in pending]
        ends = [end for _, end in pending]
        for channel, newest_end in newest.items():
            covered = self.coverage.get(channel) or (audio_starts or {}).get(channel)
            if covered is None or newest_end is None:
                continue
            gap = (
                clock.parse_iso(newest_end) - clock.parse_iso(covered)
            ).total_seconds()
            age = (now - clock.parse_iso(covered)).total_seconds()
            if gap >= 5 and age > warning_s:
                seconds += gap
                starts.append(covered)
                ends.append(covered)
        self.oldest_end = min(ends, default=None)
        return Backlog(
            count=len(pending), seconds=seconds, oldest=min(starts, default=None)
        )
