from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from odsod_daemon.lib import audio, clock

HOUR = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)


def write_hour(root: Path, channel: str, hour: datetime, data: bytes) -> Path:
    path = audio.hour_file(root, channel, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_hour_file_name(tmp_path: Path) -> None:
    path = audio.hour_file(tmp_path, "mic", datetime(2026, 11, 22, 14, 59, tzinfo=UTC))
    assert path == tmp_path / "audio" / "mic" / "20261122T14Z.pcm"


def test_cut_inside_one_hour(tmp_path: Path) -> None:
    data = bytes(range(256)) * 1000
    write_hour(tmp_path, "mic", HOUR, data)
    start = HOUR + timedelta(seconds=1)
    end = HOUR + timedelta(seconds=2)
    result = audio.cut(tmp_path, "mic", start, end)
    assert result == data[audio.BYTES_PER_SECOND : 2 * audio.BYTES_PER_SECOND]


def test_cut_across_hours(tmp_path: Path) -> None:
    write_hour(
        tmp_path,
        "sys",
        HOUR,
        b"\0" * (audio.BYTES_PER_SECOND * 3599 + 16_000) + b"a" * 16_000,
    )
    write_hour(tmp_path, "sys", HOUR + timedelta(hours=1), b"b" * 16_000)
    result = audio.cut(
        tmp_path,
        "sys",
        HOUR + timedelta(seconds=3599.5),
        HOUR + timedelta(hours=1, seconds=0.5),
    )
    assert result == b"a" * 16_000 + b"b" * 16_000


def test_cut_a_hole_reads_as_zeros(tmp_path: Path) -> None:
    result = audio.cut(
        tmp_path, "mic", HOUR + timedelta(seconds=1), HOUR + timedelta(seconds=2)
    )
    assert result == bytes(audio.BYTES_PER_SECOND)


def test_cut_empty_range(tmp_path: Path) -> None:
    assert audio.cut(tmp_path, "mic", HOUR, HOUR) == b""


def test_covered_until_uses_file_size(tmp_path: Path) -> None:
    write_hour(tmp_path, "mic", HOUR, b"\0" * (audio.BYTES_PER_SECOND * 5))
    assert audio.covered_until(tmp_path, "mic") == HOUR + timedelta(seconds=5)


def test_covered_until_uses_newest_file(tmp_path: Path) -> None:
    write_hour(tmp_path, "mic", HOUR, b"\0" * audio.BYTES_PER_SECOND)
    write_hour(
        tmp_path, "mic", HOUR + timedelta(hours=1), b"\0" * (audio.BYTES_PER_SECOND * 2)
    )
    assert audio.covered_until(tmp_path, "mic") == HOUR + timedelta(hours=1, seconds=2)


def test_covered_until_without_files(tmp_path: Path) -> None:
    assert audio.covered_until(tmp_path, "mic") is None


async def test_wait_until_returns_when_covered(tmp_path: Path) -> None:
    write_hour(tmp_path, "mic", HOUR, b"\0" * (audio.BYTES_PER_SECOND * 5))
    await audio.wait_until(tmp_path, "mic", HOUR + timedelta(seconds=5))


async def test_wait_until_waits_for_new_bytes(tmp_path: Path) -> None:
    path = write_hour(tmp_path, "mic", HOUR, b"\0" * audio.BYTES_PER_SECOND)

    async def extend() -> None:
        await clock.sleep(1)
        path.write_bytes(b"\0" * (audio.BYTES_PER_SECOND * 2))

    task = asyncio.create_task(extend())
    await audio.wait_until(
        tmp_path, "mic", HOUR + timedelta(seconds=2), poll_s=0.2, timeout_s=5
    )
    await task


async def test_wait_until_times_out(tmp_path: Path) -> None:
    with pytest.raises(TimeoutError):
        await audio.wait_until(
            tmp_path, "mic", HOUR + timedelta(seconds=2), poll_s=0.2, timeout_s=1
        )
