"""One ``pw-record`` subprocess per channel: read 100 ms blocks, restart."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

from odsod_daemon.components.capture.anchor import (
    BLOCK_BYTES,
    GAP_THRESHOLD_S,
    Anchor,
)
from odsod_daemon.components.capture.config import CaptureConfig
from odsod_daemon.components.capture.contract import CAPTURE_APP_NAME, Channel
from odsod_daemon.components.capture.writer import Writer
from odsod_daemon.lib import clock

STOP_GRACE_S = 0.5


class Process(Protocol):
    @property
    def stdout(self) -> asyncio.StreamReader: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    async def wait(self) -> int: ...


Spawn = Callable[[Channel], Awaitable[Process]]


class Sink(Protocol):
    """What the channel reports while it runs."""

    def start(
        self, channel: Channel, audio_start: float, prev_end: float | None
    ) -> None: ...

    def gap(self, channel: Channel, start: float, end: float, reason: str) -> None: ...

    def stop(self, channel: Channel) -> None: ...

    def block(self, channel: Channel, block: bytes, start: float) -> None: ...


class _Interrupted(Exception):
    """The stopping event woke the read."""


class _Stalled(Exception):
    """No block arrived inside the stall window."""


class _Restart(Exception):
    """A suspend asked for a new process."""


def stream_arguments(channel: Channel) -> list[str]:
    """The ``pw-record`` arguments of one channel (ADR-0011 "Channels")."""
    properties = [
        f"application.name = {CAPTURE_APP_NAME}",
        f"node.name = {CAPTURE_APP_NAME}-{channel}",
    ]
    if channel == "sys":
        properties.insert(0, "stream.capture.sink = true")
    return [
        "pw-record",
        "--rate",
        "16000",
        "--channels",
        "1",
        "--format",
        "s16",
        "--raw",
        "-P",
        "{ " + " ".join(properties) + " }",
        "-",
    ]


async def spawn(channel: Channel) -> Process:
    """Start one ``pw-record`` and give it its own stderr."""
    process = await asyncio.create_subprocess_exec(
        *stream_arguments(channel),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdout is not None
    return cast(Process, process)


class ChannelLoop:
    """The block loop of one channel, with its own anchor and writer."""

    def __init__(
        self,
        name: Channel,
        writer: Writer,
        config: CaptureConfig,
        sink: Sink,
        *,
        spawner: Spawn = spawn,
    ) -> None:
        self.name: Channel = name
        self.writer = writer
        self.config = config
        self.sink = sink
        self.spawner = spawner
        self._config = config
        self.prev_end = writer.end()
        self.audio_end = self.prev_end
        self.last_arrival: float | None = None
        self.wrote_audio = False
        self._restart_reason: str | None = None
        self.restart_event = asyncio.Event()
        self._new_anchor()

    def request_restart(self, reason: str) -> None:
        """Restart the process now."""
        self._restart_reason = reason
        self.restart_event.set()

    def _take_restart(self) -> str | None:
        if not self.restart_event.is_set():
            return None
        self.restart_event.clear()
        reason = self._restart_reason or "suspend"
        self._restart_reason = None
        return reason

    def stall_start(self, service_start: float) -> float:
        if self.audio_end is None:
            return service_start
        return max(self.audio_end, service_start)

    async def run(self, stopping: asyncio.Event) -> None:
        resumed: str | None = None
        while not stopping.is_set():
            self._new_anchor()
            process = await self.spawner(self.name)
            reason = await self._blocks(process, stopping, resumed)
            if stopping.is_set():
                break
            if reason is None:
                resumed = None
                await _sleep(stopping, self.config.stall_restart_s)
            else:
                resumed = reason

    def _new_anchor(self) -> None:
        self.anchor = Anchor(
            latency_ms=self._config.capture_latency_ms,
            reanchor_ms=self._config.reanchor_ms,
        )

    async def _blocks(
        self, process: Process, stopping: asyncio.Event, resumed: str | None = None
    ) -> str | None:
        reason: str | None = None
        first = True
        try:
            while not stopping.is_set() and reason is None:
                reason = self._take_restart()
                if reason is not None:
                    break
                try:
                    block = await _read_block(
                        process,
                        self.config.stall_restart_s,
                        stopping,
                        self.restart_event,
                    )
                except _Interrupted:
                    return None
                except _Restart:
                    reason = self._take_restart() or "suspend"
                    break
                except _Stalled:
                    reason = "stall"
                    break
                except asyncio.IncompleteReadError, ConnectionResetError:
                    return None
                arrival = clock.wall()
                placement = self.anchor.place(arrival)
                if placement.dropped:
                    continue
                prev_end = self.writer.end() if first else None
                self.writer.write(placement.start, block)
                if first:
                    if resumed is not None:
                        self._gap(placement.start, resumed)
                    self.sink.start(self.name, placement.start, prev_end)
                    first = False
                    self.wrote_audio = True
                elif placement.hole >= GAP_THRESHOLD_S:
                    self.sink.gap(
                        self.name,
                        placement.start - placement.hole,
                        placement.start,
                        "clock",
                    )
                self.audio_end = placement.end
                self.last_arrival = arrival
                self.sink.block(self.name, block, placement.start)
        finally:
            await stop_process(process)
        return reason

    def _gap(self, audio_start: float, reason: str) -> None:
        """Write the hole from the old audio end to a restarted process."""
        if self.audio_end is None or audio_start <= self.audio_end:
            return
        self.sink.gap(self.name, self.audio_end, audio_start, reason)


async def _read_block(
    process: Process,
    stall_s: float,
    stopping: asyncio.Event,
    restart: asyncio.Event,
) -> bytes:
    reading = asyncio.create_task(process.stdout.readexactly(BLOCK_BYTES))
    waiting = asyncio.create_task(stopping.wait())
    restarting = asyncio.create_task(restart.wait())
    tasks = (reading, waiting, restarting)
    try:
        done, _ = await asyncio.wait(
            set(tasks),
            timeout=stall_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not done:
        raise _Stalled
    if waiting in done:
        raise _Interrupted
    if restarting in done:
        raise _Restart
    return reading.result()


async def stop_process(process: Process) -> None:
    """Terminate a process, kill it if it ignores SIGTERM."""
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    try:
        async with clock.timeout(STOP_GRACE_S):
            await process.wait()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(ProcessLookupError):
            await process.wait()


async def _sleep(stopping: asyncio.Event, seconds: float) -> None:
    try:
        async with clock.timeout(seconds):
            await stopping.wait()
    except TimeoutError:
        pass
