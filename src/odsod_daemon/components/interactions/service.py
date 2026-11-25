"""Follow inputs, detect boundaries and drain gated work."""

import asyncio
import bisect
import json
import os
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from odsod_daemon.components.interactions import batch
from odsod_daemon.components.interactions.boundaries import Boundary, Record, at, detect
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import Interaction, MeetingRef
from odsod_daemon.lib import clock, config, healthfile, paths, streams

SOURCES = (
    "utterances/ambient",
    "utterances/dictation",
    "coverage",
    "text",
    "events/signals",
    "events/user",
    "events/capture",
    "interactions",
)
# Detection reads the whole retention window (about 1 s on a busy day), and
# coverage records mark the view dirty several times a second. Interactions are
# batch work, so a boundary found up to 30 s late costs nothing.
DETECT_EVERY_S = 30.0
BOUNDARY_KINDS = {
    "utterance",
    "covered",
    "pin",
    "meeting-start",
    "meeting-end",
    "start",
    "gap",
    "stop",
    "interaction",
}


def local_zone() -> ZoneInfo:
    name = os.environ.get("TZ")
    if not name:
        name = str(Path("/etc/localtime").resolve()).split("/zoneinfo/")[-1]
    return ZoneInfo(name)


class View:
    """Keep sorted input records; stream followers insert only new records."""

    def __init__(self, roots: paths.Roots, days: int):
        self.roots = roots
        self.days = days
        self.data: dict[str, list[Record]] = {name: [] for name in SOURCES}
        self.seen: set[tuple[str, str]] = set()
        self.tasks: dict[Path, asyncio.Task] = {}
        self.changed = asyncio.Event()
        self.dirty = True
        self.day = clock.utc_now().date()

    def insert(self, source: str, record: Record) -> None:
        signature = source, json.dumps(record, sort_keys=True)
        if signature in self.seen:
            return
        self.seen.add(signature)
        bisect.insort_right(self.data[source], record, key=at)
        if record["kind"] in BOUNDARY_KINDS and source != "utterances/dictation":
            self.dirty = True
        self.changed.set()

    def load(self) -> None:
        first = clock.utc_now().date() - timedelta(days=self.days)
        for source in SOURCES:
            for path in sorted((self.roots.state / source).glob("*.jsonl")):
                if first.isoformat() <= path.stem:
                    for record in streams.read_day(path):
                        self.insert(source, record)

    async def follow(self, source: str, path: Path) -> None:
        async for record in streams.follow(path, start_at_end=False, scan_s=5):
            self.insert(source, record)

    def refresh(self) -> None:
        today = clock.utc_now().date()
        first = today - timedelta(days=self.days)
        if self.day != today:
            for source in SOURCES:
                self.data[source] = [
                    r for r in self.data[source] if at(r).date() >= first
                ]
            self.seen = {
                (source, json.dumps(r, sort_keys=True))
                for source in SOURCES
                for r in self.data[source]
            }
            for path in list(self.tasks):
                if path.stem < first.isoformat():
                    self.tasks.pop(path).cancel()
            self.dirty = True
            self.day = today
        for source in SOURCES:
            directory = self.roots.state / source
            candidates = set(directory.glob("*.jsonl"))
            candidates.add(streams.day_path(directory, today))
            candidates.add(streams.day_path(directory, today + timedelta(days=1)))
            for path in candidates:
                if path.stem >= first.isoformat() and path not in self.tasks:
                    self.tasks[path] = asyncio.create_task(self.follow(source, path))
        for task in self.tasks.values():
            if task.done():
                task.result()  # Propagate unexpected reader failures to the pipeline.

    async def close(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


class Worker:
    def __init__(self, settings: InteractionsConfig, roots: paths.Roots):
        self.config = settings
        self.roots = roots
        self.common = config.load_common(roots)
        self.view = View(roots, self.common.retention_days)
        self.view.load()
        self.boundaries: list[Boundary] = []
        self.zone = local_zone()
        self.detected_at = float("-inf")

    def pending(self) -> list[Boundary]:
        data = self.view.data
        now = clock.utc_now()
        stale = self.view.dirty or any(
            e["kind"] == "stop" for e in data["events/capture"]
        )
        if stale and clock.monotonic() - self.detected_at >= DETECT_EVERY_S:
            self.detected_at = clock.monotonic()
            done = data["interactions"]
            # Start at the newest done interaction's start, not its end: it is
            # found again (same ID, skipped as done), and an utterance that
            # overlaps its end after a split is kept for the next one.
            latest = max(done, key=lambda r: r["end"], default=None)
            newest = clock.parse_iso(latest["start"]) if latest else None
            first = now - timedelta(days=self.common.retention_days)
            utterances = [
                u
                for u in data["utterances/ambient"]
                if clock.parse_iso(u["start"]) >= first
                and (newest is None or clock.parse_iso(u["start"]) >= newest)
            ]
            self.boundaries = detect(
                utterances,
                data["events/signals"] + data["events/user"],
                data["coverage"],
                data["events/capture"],
                now,
                self.config,
            )
            self.view.dirty = False
        done_ids = {r["id"] for r in data["interactions"]}
        spans = [
            (clock.parse_iso(r["start"]), clock.parse_iso(r["end"]))
            for r in data["interactions"]
        ]
        # A done interaction that straddles the retention start is found again
        # without its first utterances, under a new ID: skip it by its span.
        return [
            b
            for b in self.boundaries
            if b.id not in done_ids
            and not any(s <= b.start and b.end <= e for s, e in spans)
        ]

    def waiting(self, todo: list[Boundary]) -> None:
        health = healthfile.HealthFile(
            self.roots.run / "health/pipeline.json", "pipeline"
        )
        old = [
            b
            for b in todo
            if (clock.utc_now() - b.end).total_seconds()
            > self.config.waiting_warn_h * 3600
        ]
        if old:
            oldest = min(b.end for b in old).astimezone(self.zone).isoformat()
            health.set(
                "interactions-waiting",
                f"{len(old)} interaction documents waiting since {oldest}",
            )
        else:
            health.clear("interactions-waiting")
        health.rewrite()

    def step(self) -> bool:
        todo = self.pending()
        self.waiting(todo)
        if not todo:
            return False
        data = self.view.data
        first = clock.utc_now() - timedelta(days=self.common.retention_days)
        ambient = [u for u in data["utterances/ambient"] if at(u) >= first]
        dictation = [u for u in data["utterances/dictation"] if at(u) >= first]
        if not batch.gate(ambient, dictation, data["text"]):
            return False
        boundary = todo[0]
        try:
            batch.process(
                boundary,
                data["text"],
                data["events/signals"] + data["events/user"],
                self.config,
                self.roots,
                self.common.host,
                self.zone,
            )
        except ValueError as error:
            # A bad document front matter or meeting record: the same inputs
            # fail again, so the interaction is done with no retry.
            self.failed(boundary, error)
        # Include our writes now, without waiting for a follower wakeup.
        for record in batch.records(self.roots.state / "interactions"):
            self.view.insert("interactions", record)
        self.waiting(self.pending())
        return True

    def failed(self, boundary: Boundary, error: Exception) -> None:
        batch.append(
            self.roots.state / "interactions",
            Interaction(
                ts=clock.iso(),
                id=boundary.id,
                start=clock.iso(boundary.start),
                end=clock.iso(boundary.end),
                outcome="failed",
                end_cause=boundary.end_cause,
                meeting=None
                if boundary.meeting is None
                else MeetingRef.model_validate(boundary.meeting),
                error=" ".join(str(error).splitlines()),
            ).model_dump(mode="json"),
        )


async def run(settings: InteractionsConfig, *, once: bool = False) -> None:
    worker = Worker(settings, paths.roots())
    try:
        while True:
            if not once:
                worker.view.refresh()
            if worker.step():
                # Yield, so a backlog does not starve the other components.
                await asyncio.sleep(0)
                continue
            if once:
                return
            worker.view.changed.clear()
            try:
                async with clock.timeout(5):
                    await worker.view.changed.wait()
            except TimeoutError:
                pass
    finally:
        await worker.view.close()
