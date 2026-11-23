from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from odsod_daemon.lib import pending

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def item(identifier: str, hours_ago: float) -> pending.Input:
    return pending.Input(identifier, NOW - timedelta(hours=hours_ago))


def test_pending_is_oldest_first() -> None:
    inputs = [item("b", 2), item("a", 3), item("c", 1)]
    assert pending.pending_ids(inputs, [], now=NOW, retention_days=14) == [
        "a",
        "b",
        "c",
    ]


def test_outputs_are_done() -> None:
    inputs = [item("a", 1), item("b", 1)]
    assert pending.pending_ids(inputs, ["a"], now=NOW, retention_days=14) == ["b"]


def test_inputs_outside_the_window_are_not_pending() -> None:
    inputs = [item("old", 24 * 15), item("new", 1)]
    assert pending.pending_ids(inputs, [], now=NOW, retention_days=14) == ["new"]


def test_expired_ids() -> None:
    inputs = [item("old", 24 * 15), item("new", 1)]
    assert pending.expired_ids(inputs, [], now=NOW, retention_days=14) == ["old"]
    assert pending.expired_ids(inputs, ["old"], now=NOW, retention_days=14) == []


def test_retry_policy_delays() -> None:
    policy = pending.RetryPolicy(attempts=4, base_delay_s=0.5, factor=2, max_delay_s=3)
    assert pending.delays(policy) == [0.5, 1.0, 2.0]


async def test_retry_returns_first_success() -> None:
    calls = 0

    async def call() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert await pending.retry(call, pending.RetryPolicy()) == "ok"
    assert calls == 1


async def test_retry_uses_backoff_and_raises() -> None:
    delays: list[float] = []
    calls = 0

    async def call() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("nope")

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    with pytest.raises(RuntimeError, match="nope"):
        await pending.retry(
            call,
            pending.RetryPolicy(attempts=3, base_delay_s=0.5, factor=2),
            sleep=sleep,
        )
    assert calls == 3
    assert delays == [0.5, 1.0]


async def test_retry_succeeds_after_failure() -> None:
    calls = 0

    async def call() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("once")
        return "ok"

    assert (
        await pending.retry(
            call, pending.RetryPolicy(attempts=2), sleep=lambda _seconds: _noop()
        )
        == "ok"
    )
    assert calls == 2


async def _noop() -> None:
    return None
