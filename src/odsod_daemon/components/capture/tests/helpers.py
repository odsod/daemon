"""Fakes and record readers for the capture component tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path

from odsod_daemon.components.capture.anchor import BLOCK_BYTES
from odsod_daemon.components.capture.contract import Channel
from odsod_daemon.components.capture.source import SourceState
from odsod_daemon.lib import clock, documents, streams

WALL_BASE = 1_800_000_000.0

Feed = Callable[[asyncio.StreamReader], Coroutine[object, object, None]]


class FakeProcess:
    """A process whose stdout a test feeds on the virtual clock."""

    def __init__(self, feed: Feed | None) -> None:
        self.stdout = asyncio.StreamReader()
        self.terminated = False
        self._exited = asyncio.Event()
        self._task = asyncio.ensure_future(feed(self.stdout)) if feed else None

    def terminate(self) -> None:
        self.terminated = True
        if self._task is not None:
            self._task.cancel()
        if not self.stdout.at_eof():
            self.stdout.feed_eof()
        self._exited.set()

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int:
        await self._exited.wait()
        return 0


class FakePwRecord:
    """Spawn a scripted fake per channel, in order."""

    def __init__(self) -> None:
        self.scripts: dict[str, list[Feed | None]] = {"mic": [], "sys": []}
        self.processes: list[FakeProcess] = []
        self.spawns: list[str] = []

    def script(self, channel: Channel, *feeds: Feed | None) -> None:
        self.scripts[channel].extend(feeds)

    async def __call__(self, channel: Channel) -> FakeProcess:
        self.spawns.append(channel)
        pending = self.scripts[channel]
        feed = pending.pop(0) if pending else None
        process = FakeProcess(feed)
        self.processes.append(process)
        return process


def feed_blocks(
    count: int, *, value: int = 1, delay: float = 0.1, eof: bool = False
) -> Feed:
    """Feed ``count`` blocks of one int16 sample at one block per delay."""
    sample = value.to_bytes(2, "little", signed=True) * (BLOCK_BYTES // 2)

    async def feed(reader: asyncio.StreamReader) -> None:
        for _ in range(count):
            reader.feed_data(sample)
            await clock.sleep(delay)
        if eof:
            reader.feed_eof()

    return feed


class FakeSource:
    """A default source whose mute flag a test can change."""

    def __init__(self, *, muted: bool = False) -> None:
        self.state = SourceState(name="fake_mic", muted=muted)
        self.reports: list[SourceState] = []

    def set_muted(self, muted: bool) -> None:
        self.state = SourceState(name=self.state.name, muted=muted)

    async def __call__(
        self, on_state: Callable[[SourceState], None], stopping: asyncio.Event
    ) -> None:
        while not stopping.is_set():
            on_state(self.state)
            self.reports.append(self.state)
            try:
                async with clock.timeout(0.1):
                    await stopping.wait()
            except TimeoutError:
                pass


def read_records(root: Path) -> list[dict]:
    directory = root / "state" / "events" / "capture"
    records: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        records.extend(streams.read_day(path))
    return records


def records_of(root: Path, kind: str, channel: str | None = None) -> list[dict]:
    return [
        record
        for record in read_records(root)
        if record["kind"] == kind and (channel is None or record["channel"] == channel)
    ]


def health_faults(root: Path) -> list[dict]:
    path = root / "run" / "health" / "capture.json"
    if not path.exists():
        return []
    return documents.read_json(path)["faults"]
