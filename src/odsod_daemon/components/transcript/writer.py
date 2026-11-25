"""Follow input streams and append complete lines with their checkpoint keys."""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from odsod_daemon.components.transcript import days, echo, gaps, lines
from odsod_daemon.components.transcript.config import TranscriptConfig, local_zone
from odsod_daemon.components.transcript.contract import (
    FinishedTranscript,
    Line,
    parse_file,
)
from odsod_daemon.lib import clock, config, documents, paths, streams

INPUTS = (
    "text",
    "events/signals",
    "events/user",
    "events/capture",
    "utterances/ambient",
    "utterances/dictation",
    "coverage",
)
log = logging.getLogger(__name__)


class Writer:
    def __init__(self, settings: TranscriptConfig):
        self.settings = settings
        self.roots = paths.roots()
        common = config.load_common()
        self.host = config.host_name()
        self.retention = common.retention_days
        self.zone = local_zone()
        self.directory = self.roots.state / "documents/transcripts"
        self.closed = {
            record["document"]
            for file in (self.roots.state / "finished/transcript").glob("*.jsonl")
            for record in streams.read_day(file)
        }
        self.keys: dict[date, set[str]] = {}
        # Echo drops are final: decide each once, not on every flush.
        self.dropped: dict[date, set[str]] = {}
        self.logged: set[str] = set()
        self.recover()

    def read(self, stream: str, now: datetime) -> list[dict]:
        return streams.read_days(
            self.roots.state / stream,
            now.date() - timedelta(days=self.retention + 1),
            now.date(),
        )

    def path(self, day: date) -> Path:
        return self.directory / f"{day.isoformat()}-{self.host}.md"

    def recover(self) -> None:
        for path in self.directory.glob(f"*-{self.host}.md"):
            if path.name in self.closed:
                continue
            data = path.read_bytes()
            if not data.endswith(b"\n"):
                data = data[: data.rfind(b"\n") + 1]
                with path.open("r+b") as handle:
                    handle.truncate(len(data))
            day = date.fromisoformat(path.name[:10])
            self.keys[day] = {line.key for line in parse_file(data.decode())}

    def append(self, line: Line) -> None:
        day = line.time.astimezone(self.zone).date()
        path = self.path(day)
        if path.name in self.closed:
            if line.key not in self.logged:
                log.info(
                    "ignore line %s for finished transcript %s", line.key, path.name
                )
                self.logged.add(line.key)
            return
        keys = self.keys.setdefault(day, set())
        if line.key in keys:
            return
        if not path.exists():
            documents.write(
                path,
                f"---\ntype: transcript\nhost: {self.host}\ndate: {day}\n"
                f"timezone: {self.zone.key}\n---\n\n"
                f"# Transcript {day}, {self.host}\n\n",
            )
        data = (line.render() + "\n").encode()
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            if os.write(fd, data) != len(data):
                raise OSError("partial transcript line write")
        finally:
            os.close(fd)
        keys.add(line.key)

    def flush(self, now: datetime | None = None) -> None:
        now = now or clock.utc_now()
        inputs = {stream: self.read(stream, now) for stream in INPUTS}
        texts = inputs["text"]
        utterances = inputs["utterances/ambient"] + inputs["utterances/dictation"]
        off = gaps.ranges(inputs["events/capture"], now)
        coverage = {}
        for record in inputs["coverage"]:
            channel, end = record["channel"], clock.parse_iso(record["end"])
            coverage[channel] = max(coverage.get(channel, end), end)
        candidates: list[tuple[datetime, Line]] = []
        held: set[date] = set()
        relevant = set(self.keys)
        for record in utterances:
            relevant.add(clock.parse_iso(record["start"]).astimezone(self.zone).date())
        for record in sorted(
            texts + inputs["events/user"] + inputs["events/signals"],
            key=lambda r: r["ts"],
        ):
            line = lines.from_record(record, self.zone)
            if line is None:
                continue
            day = line.time.date()
            relevant.add(day)
            if line.key in self.keys.get(day, set()) or line.key in self.dropped.get(
                day, set()
            ):
                continue
            # A finished day takes no lines (append ignores them): skip the check.
            if line.tag == "mic" and self.path(day).name not in self.closed:
                decision = echo.decide(
                    record, utterances, texts, coverage, now, self.settings
                )
                if decision == "drop":
                    self.dropped.setdefault(day, set()).add(line.key)
                    continue
                capped = now >= days.bounds(day, self.zone)[1] + timedelta(
                    hours=self.settings.finish_cap_h
                )
                if decision == "hold" and not capped:
                    held.add(day)
                    continue
            candidates.append((clock.parse_iso(record["ts"]), line))
        for line in gaps.lines(
            off,
            inputs["events/user"],
            inputs["events/capture"],
            self.settings,
            self.zone,
        ):
            relevant.add(line.time.date())
            # A gap arrives when it closes, after already-arrived speech and events.
            candidates.append((now, line))
        cutoff = now.astimezone(self.zone).date() - timedelta(days=self.retention)
        for _, line in sorted(candidates, key=lambda pair: pair[0]):
            if line.time.date() >= cutoff:
                self.append(line)
        for day in sorted(relevant):
            if day < cutoff or self.path(day).name in self.closed:
                continue
            pending = days.missing(day, self.zone, utterances, texts)
            decision = days.finish(
                day, self.zone, now, coverage, off, pending, day in held, self.settings
            )
            if decision is None:
                continue
            if decision == "cap":
                for line in days.capped_lines(pending, self.zone):
                    self.append(line)
            if not self.path(day).exists():
                continue
            record = FinishedTranscript(
                ts=clock.iso(now),
                document=self.path(day).name,
                day=day.isoformat(),
                capped=decision == "cap",
            )
            streams.append(
                streams.day_path(self.roots.state / "finished/transcript", now.date()),
                record.model_dump(mode="json"),
            )
            self.closed.add(record.document)


async def _follow(path: Path, wake: asyncio.Event) -> None:
    async for _ in streams.follow(path, start_at_end=False):
        wake.set()


async def run(settings: TranscriptConfig, *, once: bool = False) -> None:
    writer = Writer(settings)
    if once:
        writer.flush()
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
                            streams.day_path(writer.roots.state / stream, day), wake
                        )
                    )
                    for stream in INPUTS
                    for day in (today, today + timedelta(days=1))
                ]
                watched_day = today
            wake.clear()
            writer.flush()
            try:
                async with clock.timeout(1):
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
