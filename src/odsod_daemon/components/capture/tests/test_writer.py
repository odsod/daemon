"""Table tests for the hour writer (ADR-0003 "Audio")."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.capture.writer import Writer
from odsod_daemon.lib import audio

HOUR = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)


def _at(offset_s: float) -> float:
    return (HOUR + timedelta(seconds=offset_s)).timestamp()


def test_offset_is_time_and_the_hole_reads_as_zeros(tmp_path: Path) -> None:
    writer = Writer(tmp_path, "mic")
    writer.write(_at(2.0), b"\x01\x02" * audio.SAMPLE_RATE * 2)
    path = audio.hour_file(tmp_path, "mic", HOUR)
    assert path.stat().st_size == 4 * audio.BYTES_PER_SECOND
    with path.open("rb") as handle:
        handle.seek(0)
        assert handle.read(2 * audio.SAMPLE_RATE) == bytes(2 * audio.SAMPLE_RATE)
    cut = audio.cut(tmp_path, "mic", HOUR, HOUR + timedelta(seconds=2))
    assert cut == bytes(2 * audio.BYTES_PER_SECOND)
    assert writer.end() == pytest.approx(_at(4.0))


def test_block_is_split_at_the_hour(tmp_path: Path) -> None:
    writer = Writer(tmp_path, "sys")
    block = b"\xaa\xbb" * (audio.SAMPLE_RATE // 10)
    writer.write(_at(3599.95), block)
    first = audio.hour_file(tmp_path, "sys", HOUR)
    second = audio.hour_file(tmp_path, "sys", HOUR + timedelta(hours=1))
    assert first.stat().st_size == audio.BYTES_PER_SECOND * 3600
    assert second.stat().st_size == 1600
    with first.open("rb") as handle:
        handle.seek(-1600, os.SEEK_END)
        assert handle.read() == block[:1600]
    with second.open("rb") as handle:
        assert handle.read() == block[1600:]


def test_writer_never_writes_backward(tmp_path: Path) -> None:
    writer = Writer(tmp_path, "mic")
    writer.write(_at(10.0), b"\x01\x00" * 100)
    writer.write(_at(5.0), b"\x02\x00" * 100)
    cut = audio.cut(
        tmp_path, "mic", HOUR + timedelta(seconds=5), HOUR + timedelta(seconds=10)
    )
    assert cut == bytes(len(cut))
    assert writer.end() == pytest.approx(_at(10.0) + 100 / audio.SAMPLE_RATE)


def test_a_partial_overlap_trims_the_front(tmp_path: Path) -> None:
    writer = Writer(tmp_path, "mic")
    writer.write(_at(1.0), b"\x01\x00" * 100)
    writer.write(_at(0.5), b"\x02\x00" * 8_700)
    path = audio.hour_file(tmp_path, "mic", HOUR)
    with path.open("rb") as handle:
        data = handle.read()
    assert len(data) == 32_000 + 1_400
    assert data[32_000:32_200] == b"\x01\x00" * 100
    assert data[32_200:] == b"\x02\x00" * 600


def test_file_and_directory_modes(tmp_path: Path) -> None:
    writer = Writer(tmp_path, "mic")
    writer.write(_at(1.0), b"\x00\x00" * 100)
    path = audio.hour_file(tmp_path, "mic", HOUR)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "audio").stat().st_mode) == 0o700
