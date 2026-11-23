"""Real-time latency check for ``streams.follow``.

CI checks p95 under 100 ms over 1,000 appends (ADR-0010, ``streams``).
"""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import time
from pathlib import Path

import pytest

from odsod_daemon.lib import streams

APPENDS = 1_000


@pytest.mark.timing
@pytest.mark.looptime(False)
async def test_follow_p95_under_100_ms(tmp_path: Path) -> None:
    path = tmp_path / "events" / "day.jsonl"
    latencies: list[float] = []
    received: asyncio.Queue[float] = asyncio.Queue()

    async def consume() -> None:
        async for _record in streams.follow(path, start_at_end=False, scan_s=5.0):
            await received.put(time.perf_counter())

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.2)
    try:
        for index in range(APPENDS):
            started = time.perf_counter()
            streams.append(path, {"n": index})
            seen = await asyncio.wait_for(received.get(), timeout=2)
            latencies.append((seen - started) * 1000)
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]
    print(f"p50={p50:.1f}ms p95={p95:.1f}ms")
    assert p95 < 100, f"p95 {p95:.1f}ms"
