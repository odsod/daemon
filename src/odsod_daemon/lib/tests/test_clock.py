from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from odsod_daemon.lib import clock


def test_iso_has_milliseconds() -> None:
    moment = datetime(2026, 11, 22, 14, 30, 5, 120000, tzinfo=UTC)
    assert clock.iso(moment) == "2026-11-22T14:30:05.120Z"


def test_parse_accepts_z_and_offsets() -> None:
    assert clock.parse_iso("2026-11-22T14:30:05.120Z") == datetime(
        2026, 11, 22, 14, 30, 5, 120000, tzinfo=UTC
    )
    assert clock.parse_iso("2026-11-22T15:30:05.120+01:00") == datetime(
        2026, 11, 22, 14, 30, 5, 120000, tzinfo=UTC
    )


def test_parse_iso_rejects_naive_as_utc() -> None:
    assert clock.parse_iso("2026-11-22T14:30:05").tzinfo is UTC


def test_wall_and_monotonic_are_numbers() -> None:
    assert clock.wall() > 0
    assert clock.monotonic() > 0
    assert clock.boottime() > 0


async def test_sleep_runs_on_virtual_time() -> None:
    start = asyncio.get_running_loop().time()
    await clock.sleep(3600)
    assert asyncio.get_running_loop().time() - start == pytest.approx(3600)


async def test_timeout_runs_on_virtual_time() -> None:
    with pytest.raises(TimeoutError):
        async with clock.timeout(1):
            await clock.sleep(2)


async def test_monotonic_uses_virtual_loop_time() -> None:
    start = clock.monotonic()
    await clock.sleep(3600)
    assert clock.monotonic() - start == pytest.approx(3600)
