"""The capture loop: channels, source watch, suspend watch and watchdog."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from odsod_daemon.components.capture import channel as channel_module
from odsod_daemon.components.capture import checks, source
from odsod_daemon.components.capture.checks import Active, MicCheck
from odsod_daemon.components.capture.config import CaptureConfig
from odsod_daemon.components.capture.contract import (
    CHANNELS,
    CaptureGap,
    CaptureStart,
    CaptureStop,
    Channel,
    GapReason,
)
from odsod_daemon.components.capture.writer import Writer
from odsod_daemon.lib import clock, healthfile, paths, streams, systemd

TICK_S = 1.0
REWRITE_S = 60.0

MESSAGES = {
    checks.CAPTURE_STALLED: "no new audio",
    checks.MIC_SILENT: "the mic gives only zeros",
    checks.MIC_MUTED: "the default source is muted",
}
FIXES: dict[str, str | None] = {
    checks.CAPTURE_STALLED: "systemctl --user restart odsod-daemon-capture.service",
    checks.MIC_SILENT: None,
    checks.MIC_MUTED: "pactl set-source-mute @DEFAULT_SOURCE@ 0",
}


def _iso(epoch: float) -> str:
    return clock.iso(datetime.fromtimestamp(epoch, UTC))


class Recorder(channel_module.Sink):
    """Write the ``events/capture`` records and feed the mic check."""

    def __init__(self, directory: Path, mic: MicCheck) -> None:
        self.directory = directory
        self.mic = mic
        self.last_block: dict[str, float | None] = {"mic": None, "sys": None}

    def start(
        self, channel: Channel, audio_start: float, prev_end: float | None
    ) -> None:
        self._append(
            CaptureStart(
                ts=clock.iso(),
                channel=channel,
                audio_start=_iso(audio_start),
                prev_end=None if prev_end is None else _iso(prev_end),
            )
        )

    def gap(self, channel: Channel, start: float, end: float, reason: str) -> None:
        self._append(
            CaptureGap(
                ts=clock.iso(),
                channel=channel,
                start=_iso(start),
                end=_iso(end),
                reason=cast(GapReason, reason),
            )
        )

    def stop(self, channel: Channel) -> None:
        self._append(CaptureStop(ts=clock.iso(), channel=channel, reason="shutdown"))

    def block(self, channel: Channel, block: bytes, start: float) -> None:
        self.last_block[channel] = clock.monotonic()
        if channel == "mic":
            self.mic.block(block, start)

    def _append(self, record: CaptureStart | CaptureStop | CaptureGap) -> None:
        path = streams.day_path(self.directory, clock.utc_now().date())
        streams.append(path, record.model_dump(mode="json"))


class Health:
    """Keep ``run/health/capture.json`` in step with the active faults."""

    def __init__(self, path: Path) -> None:
        self.file = healthfile.HealthFile(path, "capture")
        self._active: dict[tuple[str, str | None], float] = {}
        self._last_write = 0.0

    def flush(self, active: list[Active], now: float, *, force: bool = False) -> None:
        current = {(item.code, item.key): item.since for item in active}
        stale = now - self._last_write >= REWRITE_S
        if current == self._active and not stale and not force:
            return
        for fault in list(self.file.faults):
            if (fault.code, fault.key) not in current:
                self.file.clear(fault.code, key=fault.key)
        for (code, key), since in current.items():
            self.file.set(
                code,
                MESSAGES[code],
                key=key,
                fix=FIXES.get(code),
                since=_iso(since),
            )
        self.file.rewrite()
        self._active = current
        self._last_write = now


async def run(
    config: CaptureConfig | None = None,
    *,
    state_root: Path | None = None,
    run_root: Path | None = None,
    spawner: channel_module.Spawn | None = None,
    watcher: source.Watcher | None = None,
    stopping: asyncio.Event | None = None,
    once: bool = False,
) -> None:
    """Run until the stopping event is set."""
    config = config or CaptureConfig()
    roots = paths.roots()
    state = state_root or roots.state
    run_dir = run_root or roots.run
    own_stopping = stopping is None
    stopping = stopping if stopping is not None else asyncio.Event()
    if own_stopping:
        _install_signals(stopping)

    service_start = clock.wall()
    mic = MicCheck(config.mic_silent_s)
    recorder = Recorder(state / "events" / "capture", mic)
    health = Health(run_dir / "health" / "capture.json")
    loops = {
        name: channel_module.ChannelLoop(
            name,
            Writer(state, name),
            config,
            recorder,
            spawner=spawner or channel_module.spawn,
        )
        for name in CHANNELS
    }
    floor = checks.stall_floor(
        _last_event(state / "events" / "capture"),
        max((e for e in (lp.audio_end for lp in loops.values()) if e), default=None),
        service_start,
    )

    def on_source(state_now: source.SourceState) -> None:
        mic.set_muted(state_now.muted, clock.wall())

    active = watcher or source.watch

    async def health_loop() -> None:
        while not stopping.is_set():
            now = clock.wall()
            faults: list[Active] = []
            starting = floor is None and now - service_start < checks.START_GRACE_S
            for name, loop in loops.items():
                if starting:
                    break  # No block yet is normal; a stall from before waits.
                start = checks.stall_start(loop.audio_end, service_start, floor=floor)
                if checks.is_stalled(start, now, config.stall_error_s):
                    faults.append(Active(checks.CAPTURE_STALLED, start, key=name))
            faults.extend(mic.faults(now))
            health.flush(faults, now)
            if checks.watchdog_ok(recorder.last_block, clock.monotonic()):
                systemd.sd_notify("WATCHDOG=1")
            if await _sleep(stopping, TICK_S):
                return

    async def source_loop() -> None:
        await active(on_source, stopping)

    async def suspend_loop() -> None:
        baseline = clock.boottime() - clock.monotonic()
        while not await _sleep(stopping, TICK_S):
            current = clock.boottime() - clock.monotonic()
            if current - baseline > 1.0:
                for loop in loops.values():
                    loop.request_restart("suspend")
            baseline = current

    async with asyncio.TaskGroup() as group:
        group.create_task(health_loop())
        group.create_task(source_loop())
        group.create_task(suspend_loop())
        for loop in loops.values():
            group.create_task(loop.run(stopping))
    for loop in loops.values():
        if loop.wrote_audio:
            recorder.stop(loop.name)


def _install_signals(stopping: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, stopping.set)


async def _sleep(stopping: asyncio.Event, seconds: float) -> bool:
    """Sleep, or wake early. True when the stopping event is set."""
    try:
        async with clock.timeout(seconds):
            await stopping.wait()
    except TimeoutError:
        return False
    return True


def _last_event(directory: Path) -> str | None:
    """The kind of the newest capture event of today or yesterday (UTC)."""
    today = clock.utc_now().date()
    events = streams.read_days(directory, today - timedelta(days=1), today)
    return events[-1]["kind"] if events else None
