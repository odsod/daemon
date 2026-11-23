"""Pending work derived from input IDs and output IDs.

The pending window is the retention period. Older inputs are never pending.
Retries are bounded and use exponential backoff.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from odsod_daemon.lib import clock, config


@dataclass(frozen=True)
class Input:
    id: str
    at: datetime


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_s: float = 0.5
    factor: float = 2.0
    max_delay_s: float = 8.0

    def delay(self, failed_attempt: int) -> float:
        delay = self.base_delay_s * self.factor ** (failed_attempt - 1)
        return min(delay, self.max_delay_s)


def in_window(moment: datetime, *, now: datetime, retention_days: int) -> bool:
    cutoff = now.astimezone(UTC) - timedelta(days=retention_days)
    return moment.astimezone(UTC) >= cutoff


def _window(retention_days: int | None) -> int:
    """The pending window: the given days, or ``common.retention_days``."""
    if retention_days is not None:
        return retention_days
    return config.load_common().retention_days


def pending_ids(
    inputs: Iterable[Input],
    outputs: Iterable[str],
    *,
    now: datetime,
    retention_days: int | None = None,
) -> list[str]:
    """Input IDs with no output, oldest first, inside the pending window."""
    window = _window(retention_days)
    done = set(outputs)
    pending = [
        item
        for item in inputs
        if item.id not in done and in_window(item.at, now=now, retention_days=window)
    ]
    pending.sort(key=lambda item: (item.at, item.id))
    return [item.id for item in pending]


def expired_ids(
    inputs: Iterable[Input],
    outputs: Iterable[str],
    *,
    now: datetime,
    retention_days: int | None = None,
) -> list[str]:
    """Input IDs with no output outside the pending window."""
    window = _window(retention_days)
    done = set(outputs)
    return [
        item.id
        for item in inputs
        if item.id not in done
        and not in_window(item.at, now=now, retention_days=window)
    ]


async def retry[T](
    call: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], Awaitable[None]] = clock.sleep,
) -> T:
    """Run a call with bounded retries and exponential backoff."""
    attempts = max(1, policy.attempts)
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except Exception:
            if attempt == attempts:
                raise
            await sleep(policy.delay(attempt))
    raise AssertionError("unreachable")


def delays(policy: RetryPolicy) -> Sequence[float]:
    """The delay before each retry, in order."""
    return [policy.delay(attempt) for attempt in range(1, max(1, policy.attempts))]
