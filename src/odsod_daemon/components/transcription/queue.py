"""Pending records in priority order, with stream wakeups for live workers."""

import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import timedelta
from pathlib import Path

from odsod_daemon.components.segmentation.runner import records
from odsod_daemon.lib import clock, streams


def pending(
    inputs: list[dict], outputs: list[dict], *, field: str = "id"
) -> list[dict]:
    done = {r["input"] for r in outputs}
    unique = {r[field]: r for r in inputs if r[field] not in done}
    return sorted(
        unique.values(), key=lambda r: (r.get("channel") != "dic", r["start"], r[field])
    )


class Inbox(AbstractAsyncContextManager):
    """Wake for input writes. A timer covers midnight and missed notifications."""

    def __init__(self, directories: list[Path]):
        self.directories = directories
        self.event = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.day = None

    async def __aenter__(self):
        self.refresh()
        return self

    def refresh(self) -> None:
        today = clock.utc_now().date()
        if self.day == today:
            return
        for task in self.tasks:
            task.cancel()
        self.day = today
        self.tasks += [
            asyncio.create_task(self.watch(streams.day_path(directory, day)))
            for directory in self.directories
            for day in (today, today + timedelta(days=1))
        ]

    async def watch(self, path: Path):
        async for _ in streams.follow(path, start_at_end=False):
            self.event.set()

    def prepare(self) -> None:
        self.refresh()
        self.event.clear()

    async def wait(self) -> None:
        try:
            async with clock.timeout(2):
                await self.event.wait()
        except TimeoutError:
            pass

    async def __aexit__(self, *args):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


__all__ = ["Inbox", "pending", "records"]
