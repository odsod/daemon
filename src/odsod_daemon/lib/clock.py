"""The only source of time for components."""

from __future__ import annotations

import asyncio
import time
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def wall() -> float:
    """Seconds since the Unix epoch, wall clock."""
    return time.time()


def monotonic() -> float:
    """Seconds from an arbitrary monotonic origin."""
    try:
        return asyncio.get_running_loop().time()
    except RuntimeError:
        return time.monotonic()


def boottime() -> float:
    """Seconds since boot, including suspend."""
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def utc_now() -> datetime:
    """The current time, in UTC."""
    return datetime.now(UTC)


def iso(moment: datetime | None = None) -> str:
    """Format a UTC time as RFC 3339 with milliseconds."""
    moment = utc_now() if moment is None else moment
    moment = moment.astimezone(UTC)
    return moment.strftime(_ISO_FORMAT)[:-3] + "Z"


def parse_iso(text: str) -> datetime:
    """Parse an RFC 3339 time. A trailing ``Z`` means UTC."""
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    moment = datetime.fromisoformat(normalized)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


async def sleep(seconds: float) -> None:
    """Wait for a number of seconds on the event loop clock."""
    await asyncio.sleep(seconds)


def timeout(seconds: float | None) -> AbstractAsyncContextManager[Any]:
    """An async timeout on the event loop clock."""
    return asyncio.timeout(seconds)
