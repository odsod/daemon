"""Cut audio by time from the hourly audio buffer.

The buffer is raw signed 16-bit little-endian, 16 kHz, mono: 32,000 bytes per
second. A hole reads as zeros and uses no disk.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from odsod_daemon.lib import clock

BYTES_PER_SECOND = 32_000
SAMPLE_RATE = 16_000
CHANNELS = ("mic", "sys")
_HOUR = timedelta(hours=1)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def hour_start(moment: datetime) -> datetime:
    moment = _utc(moment)
    return moment.replace(minute=0, second=0, microsecond=0)


def hour_end(moment: datetime) -> datetime:
    return hour_start(moment) + _HOUR


def hour_file(state_root: Path, channel: str, moment: datetime) -> Path:
    start = hour_start(moment)
    return state_root / "audio" / channel / f"{start:%Y%m%dT%H}Z.pcm"


def _parse_hour(path: Path) -> datetime:
    return datetime.strptime(path.stem, "%Y%m%dT%HZ").replace(tzinfo=UTC)


def covered_until(state_root: Path, channel: str) -> datetime | None:
    """The end of the newest audio of a channel, or None."""
    directory = state_root / "audio" / channel
    try:
        files = sorted(directory.glob("*.pcm"), key=lambda path: path.name)
    except OSError:
        return None
    if not files:
        return None
    newest = files[-1]
    try:
        size = newest.stat().st_size
    except FileNotFoundError:
        return None
    return _parse_hour(newest) + timedelta(seconds=size / BYTES_PER_SECOND)


def cut(
    state_root: Path,
    channel: str,
    start: datetime,
    end: datetime,
) -> bytes:
    """Cut a half-open time range of one channel."""
    start = _utc(start)
    end = _utc(end)
    if end <= start:
        return b""
    chunks: list[bytes] = []
    cursor = start
    while cursor < end:
        file_end = hour_end(cursor)
        piece_end = min(end, file_end)
        offset = int((cursor - hour_start(cursor)).total_seconds() * BYTES_PER_SECOND)
        length = int((piece_end - cursor).total_seconds() * BYTES_PER_SECOND)
        chunks.append(
            _read_piece(hour_file(state_root, channel, cursor), offset, length)
        )
        cursor = piece_end
    return b"".join(chunks)


def _read_piece(path: Path, offset: int, length: int) -> bytes:
    if length <= 0:
        return b""
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
    except FileNotFoundError:
        data = b""
    if len(data) < length:
        data += bytes(length - len(data))
    return data


async def wait_until(
    state_root: Path,
    channel: str,
    end: datetime,
    *,
    poll_s: float = 0.2,
    timeout_s: float | None = None,
) -> None:
    """Wait until the channel's buffer covers ``end``."""
    end = _utc(end)
    if timeout_s is None:
        await _wait(state_root, channel, end, poll_s)
    else:
        async with clock.timeout(timeout_s):
            await _wait(state_root, channel, end, poll_s)


async def _wait(state_root: Path, channel: str, end: datetime, poll_s: float) -> None:
    while True:
        covered = covered_until(state_root, channel)
        if covered is not None and covered >= end:
            return
        await clock.sleep(poll_s)


def seconds_for(size: int) -> float:
    return size / BYTES_PER_SECOND


def zero_range(start: datetime, end: datetime) -> bytes:
    """Zeros of the same length as a range. A helper for fixtures."""
    return bytes(max(0, int((end - start).total_seconds() * BYTES_PER_SECOND)))


def hour_files(state_root: Path, channel: str) -> list[Path]:
    return sorted((state_root / "audio" / channel).glob("*.pcm"))
