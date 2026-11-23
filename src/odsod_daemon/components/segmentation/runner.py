"""Read the audio buffer and append utterances before coverage."""

import asyncio
from datetime import UTC, datetime, timedelta

from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.segmentation.cutter import Cutter
from odsod_daemon.components.segmentation.mask import ranges, read_limit
from odsod_daemon.components.segmentation.vad import FRAME, Vad
from odsod_daemon.lib import audio, clock, config, documents, healthfile, paths, streams


def records(directory):
    today = clock.utc_now().date()
    return streams.read_days(
        directory, today - timedelta(days=config.load_common().retention_days), today
    )


def stamp(seconds: float) -> str:
    return clock.iso(datetime.fromtimestamp(seconds, UTC))


class ChannelRunner:
    def __init__(self, channel: str, speech: Speech):
        self.channel = channel
        self.roots = paths.roots()
        self.settings = speech.segmentation.for_channel(channel)
        self.vad = Vad(self.settings.energy_floor_dbfs)
        self.cursor: float | None = None
        self.cutter: Cutter | None = None
        self.last_advance = clock.monotonic()
        self.last_covered = 0.0
        self.done = {r["id"] for r in records(self.roots.state / "utterances/ambient")}
        ends = [
            clock.parse_iso(r["end"]).timestamp()
            for stream in ("coverage", "utterances/ambient")
            for r in records(self.roots.state / stream)
            if r["channel"] == channel
        ]
        self.resume = max(ends, default=0.0)

    def append(self, stream: str, record: dict) -> None:
        now = clock.utc_now()
        streams.append(
            streams.day_path(self.roots.state / stream, now.date()),
            {"ts": clock.iso(now), **record},
        )

    def emit(self, cuts) -> None:
        for cut in cuts:
            start, end = stamp(cut.start), stamp(cut.end)
            ident = f"{self.channel}-{start.replace('-', '').replace(':', '')}"
            if ident not in self.done:
                self.append(
                    "utterances/ambient",
                    {
                        "kind": "utterance",
                        "id": ident,
                        "channel": self.channel,
                        "start": start,
                        "end": end,
                        "vad": cut.vad,
                        "cut": cut.reason,
                    },
                )
                self.done.add(ident)
            self.cover(cut.end)

    def cover(self, end: float) -> None:
        if end > self.last_covered:
            self.append(
                "coverage",
                {"kind": "covered", "channel": self.channel, "end": stamp(end)},
            )
            self.last_covered = end

    def advance(self, *, once: bool) -> None:
        files = audio.hour_files(self.roots.state, self.channel)
        if not files:
            return
        oldest = audio._parse_hour(files[0]).timestamp()
        if self.cursor is None:
            self.cursor = max(oldest, self.resume)
            self.cutter = Cutter(self.settings, self.cursor)
        assert self.cutter is not None
        newest_dt = audio.covered_until(self.roots.state, self.channel)
        assert newest_dt is not None
        newest = newest_dt.timestamp()
        status_path = self.roots.run / "status.json"
        status = documents.read_json(status_path) if status_path.exists() else {}
        limit = (
            read_limit(newest, clock.wall(), status, once=once)
            if self.channel == "mic"
            else newest
        )
        # Read masks synchronously after status, including on dictating -> idle.
        masks = (
            ranges(records(self.roots.state / "utterances/dictation"))
            if self.channel == "mic"
            else []
        )
        idle = clock.monotonic() - self.last_advance >= self.settings.idle_close_s
        advanced = False
        while self.cursor < limit:
            end = min(limit, self.cursor + FRAME / audio.SAMPLE_RATE)
            if (
                not (once or idle)
                and end - self.cursor < FRAME / audio.SAMPLE_RATE - 0.000001
            ):
                break
            overlap = next(
                ((a, b) for a, b in masks if a < end and b > self.cursor), None
            )
            if overlap:
                a, b = overlap
                if a > self.cursor:
                    end = a
                else:
                    self.emit(self.cutter.boundary(self.cursor, "mask"))
                    self.cursor = min(b, limit)
                    self.cutter.floor = self.cursor
                    self.vad.reset()
                    advanced = True
                    continue
            pcm = audio.cut(
                self.roots.state,
                self.channel,
                datetime.fromtimestamp(self.cursor, UTC),
                datetime.fromtimestamp(end, UTC),
            )
            if not any(pcm):
                self.emit(self.cutter.boundary(self.cursor, "end-of-audio"))
                self.cutter.floor = end
                self.vad.reset()
            else:
                self.emit(self.cutter.feed(self.cursor, end, self.vad.probability(pcm)))
            self.cursor = end
            advanced = True
            safe = self.cutter.safe_end
            if safe - self.last_covered >= 60:
                self.cover(safe)
        if advanced:
            self.last_advance = clock.monotonic()
        if once or idle:
            self.emit(self.cutter.boundary(self.cursor, "end-of-audio"))
            self.cover(self.cursor)


async def _channel(channel: str, speech: Speech, *, once: bool) -> None:
    worker = ChannelRunner(channel, speech)
    while True:
        await asyncio.to_thread(worker.advance, once=once)
        if once:
            return
        await clock.sleep(0.02)


async def _heartbeat() -> None:
    while True:
        # Reload on the event loop so inference faults keep their own keys.
        healthfile.HealthFile(
            paths.roots().run / "health/pipeline.json", "pipeline"
        ).rewrite()
        await clock.sleep(60)


async def run(speech: Speech, *, once: bool = False) -> None:
    async with asyncio.TaskGroup() as group:
        for channel in audio.CHANNELS:
            group.create_task(_channel(channel, speech, once=once))
        if not once:
            group.create_task(_heartbeat())
