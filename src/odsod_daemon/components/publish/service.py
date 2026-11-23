"""Deliver finished documents to each configured target."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from odsod_daemon.components.publish import deliver, pending
from odsod_daemon.components.publish.config import (
    DocumentType,
    PublishingConfig,
    Target,
)
from odsod_daemon.components.publish.contract import Delivery, PublishedStart
from odsod_daemon.lib import clock, healthfile, paths, streams

SERVICE = "pipeline"
FAULT = "target-missing"
SOURCES = ("transcript", "interactions")
TYPES: tuple[DocumentType, ...] = ("transcripts", "interactions")
log = logging.getLogger(__name__)


def _read(directory: Path) -> list[dict]:
    return [
        record
        for path in sorted(directory.glob("*.jsonl"))
        for record in streams.read_day(path)
    ]


class Publisher:
    """The delivered sets and the target streams of one process."""

    def __init__(
        self,
        settings: PublishingConfig,
        *,
        roots: paths.Roots | None = None,
        now: datetime | None = None,
    ) -> None:
        self.settings = settings
        self.roots = roots or paths.roots()
        self.health = healthfile.HealthFile(
            self.roots.run / "health/pipeline.json", SERVICE
        )
        self.delivered: dict[str, set[str]] = {}
        self.since: dict[str, datetime] = {}
        self.retry_at: dict[str, float] = {}
        moment = clock.utc_now() if now is None else now
        for target in settings.targets:
            self._open(target, moment)

    def _stream_dir(self, target: Target) -> Path:
        return self.roots.state / "published" / target.name

    def _open(self, target: Target, now: datetime) -> None:
        records = _read(self._stream_dir(target))
        start = next(
            (record for record in records if record.get("kind") == "start"), None
        )
        if start is None:
            streams.append(
                streams.day_path(self._stream_dir(target), now.date()),
                PublishedStart(ts=clock.iso(now), since=clock.iso(now)).model_dump(
                    mode="json"
                ),
            )
            since = now
        else:
            since = clock.parse_iso(start["since"])
        self.since[target.name] = since
        self.delivered[target.name] = {
            record["document"]
            for record in records
            if record.get("kind") == "delivery"
            and isinstance(record.get("document"), str)
        }

    def _finished(self) -> list[pending.Finished]:
        found: list[pending.Finished] = []
        for source in SOURCES:
            for record in _read(self.roots.state / "finished" / source):
                if record.get("kind") != "finished":
                    continue
                document = record.get("document")
                kind = record.get("type")
                if not isinstance(document, str) or kind not in TYPES:
                    continue
                path = self.roots.state / "documents" / kind / document
                if not path.is_file():
                    continue
                found.append(
                    pending.Finished(
                        document=document,
                        type=cast(DocumentType, kind),
                        at=clock.parse_iso(record["ts"]),
                        path=path,
                    )
                )
        return found

    def scan(self, *, now: datetime | None = None, mono: float | None = None) -> None:
        """Deliver every pending document, one at a time, to each due target."""
        moment = clock.utc_now() if now is None else now
        current = clock.monotonic() if mono is None else mono
        finished = self._finished()
        for target in self.settings.targets:
            due = self.retry_at.get(target.name)
            if due is not None and current < due:
                continue
            items = pending.pending(
                finished,
                self.delivered[target.name],
                since=self.since[target.name],
                types=target.types,
            )
            if not items and deliver.writable(target.dir):
                # A target that is back clears its fault with no delivery.
                self.retry_at.pop(target.name, None)
                if self.health.clear(FAULT, key=target.name):
                    self.health.rewrite()
            for item in items:
                try:
                    size, digest = deliver.copy(item.path, target.dir)
                except deliver.DocumentGone:
                    log.info("document %s vanished before delivery", item.document)
                    break
                except deliver.TargetUnavailable as error:
                    self._fault(target, error.reason, moment)
                    self.retry_at[target.name] = current + self.settings.retry_s
                    break
                self._record(target, item, size, digest, moment)
                self.delivered[target.name].add(item.document)
                self.retry_at.pop(target.name, None)
                if self.health.clear(FAULT, key=target.name):
                    self.health.rewrite()

    def _record(
        self,
        target: Target,
        item: pending.Finished,
        size: int,
        digest: str,
        now: datetime,
    ) -> None:
        record = Delivery(
            ts=clock.iso(now),
            document=item.document,
            target=target.name,
            type=item.type,
            bytes=size,
            sha256=digest,
        )
        streams.append(
            streams.day_path(self._stream_dir(target), now.date()),
            record.model_dump(mode="json"),
        )

    def _fault(self, target: Target, reason: str, now: datetime) -> None:
        self.health.set(
            FAULT,
            f"Target `{target.name}` missing or full: `{target.dir}` (`{reason}`)",
            key=target.name,
            fix=None,
            since=clock.iso(now),
        )
        self.health.rewrite()


async def _follow(path: Path, wake: asyncio.Event) -> None:
    async for _ in streams.follow(path, start_at_end=False):
        wake.set()


async def run(settings: PublishingConfig, *, once: bool = False) -> None:
    publisher = Publisher(settings)
    if once:
        publisher.scan()
        return
    wake = asyncio.Event()
    watched_day = None
    watchers: list[asyncio.Task] = []
    try:
        while True:
            today = clock.utc_now().date()
            if watched_day != today:
                for task in watchers:
                    task.cancel()
                await asyncio.gather(*watchers, return_exceptions=True)
                watchers = [
                    asyncio.create_task(
                        _follow(
                            streams.day_path(
                                publisher.roots.state / "finished" / source, day
                            ),
                            wake,
                        )
                    )
                    for source in SOURCES
                    for day in (today, today + timedelta(days=1))
                ]
                watched_day = today
            wake.clear()
            publisher.scan()
            try:
                async with clock.timeout(settings.scan_s):
                    await wake.wait()
            except TimeoutError:
                pass
            # Surface a failed follower instead of silently losing wakeups.
            for task in watchers:
                if task.done():
                    task.result()
    finally:
        for task in watchers:
            task.cancel()
        await asyncio.gather(*watchers, return_exceptions=True)
