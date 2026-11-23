"""Read the default source's mute flag, and follow ``pactl`` events."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum, auto

from odsod_daemon.lib import clock

PACTL = "pactl"
CALL_TIMEOUT_S = 5.0
RETRY_S = 5.0
POLL_S = 60.0


@dataclass(frozen=True)
class SourceState:
    name: str | None
    muted: bool


class _ReadTimeout(Enum):
    EXPIRED = auto()


class PactlError(RuntimeError):
    """A ``pactl`` call failed or gave output this code cannot read."""


OnState = Callable[[SourceState], None]
Watcher = Callable[[OnState, asyncio.Event], Awaitable[None]]


async def read_default() -> SourceState:
    """The default source's name and mute flag."""
    name = (await _call("--format=json", "get-default-source")).strip() or None
    if name is None:
        return SourceState(name=None, muted=False)
    listing = await _call("--format=json", "list", "sources")
    try:
        entries = json.loads(listing)
    except json.JSONDecodeError as error:
        raise PactlError(f"pactl gave bad JSON: {error}") from error
    for entry in entries:
        if entry.get("name") == name:
            return SourceState(name=name, muted=bool(entry.get("mute")))
    return SourceState(name=name, muted=False)


async def watch(on_state: OnState, stopping: asyncio.Event) -> None:
    """Report the mute flag at start, on each source event, and every 60 s."""
    while not stopping.is_set():
        await _report(on_state)
        try:
            process = await asyncio.create_subprocess_exec(
                PACTL,
                "subscribe",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            await _sleep(stopping, RETRY_S)
            continue
        try:
            while not stopping.is_set():
                line = await _readline(process, stopping, POLL_S)
                if line is None:
                    break
                if line is _ReadTimeout.EXPIRED or "source" in line or "server" in line:
                    await _report(on_state)
        finally:
            await _stop(process)
        await _sleep(stopping, RETRY_S)


WATCH: Watcher = watch


async def _report(on_state: OnState) -> None:
    with contextlib.suppress(PactlError, OSError):
        on_state(await read_default())


async def _call(*args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        PACTL,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with clock.timeout(CALL_TIMEOUT_S):
            stdout, _ = await process.communicate()
    except TimeoutError as error:
        await _stop(process)
        raise PactlError("pactl timed out") from error
    if process.returncode != 0:
        raise PactlError(f"pactl exited {process.returncode}")
    return stdout.decode("utf-8", "replace")


async def _readline(
    process: asyncio.subprocess.Process, stopping: asyncio.Event, timeout_s: float
) -> str | _ReadTimeout | None:
    assert process.stdout is not None
    reading = asyncio.create_task(process.stdout.readline())
    waiting = asyncio.create_task(stopping.wait())
    try:
        done, _ = await asyncio.wait(
            {reading, waiting},
            timeout=timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in (reading, waiting):
            if not task.done():
                task.cancel()
        await asyncio.gather(reading, waiting, return_exceptions=True)
    if waiting in done:
        return None
    if not done:
        return _ReadTimeout.EXPIRED
    line = reading.result()
    return line.decode("utf-8", "replace").rstrip() if line else None


async def _stop(process: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    try:
        async with clock.timeout(CALL_TIMEOUT_S):
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
