from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest

from odsod_daemon.lib import streams


def test_append_one_line(tmp_path: Path) -> None:
    path = tmp_path / "events" / "day.jsonl"
    streams.append(path, {"kind": "note", "text": "hej"})
    assert path.read_text(encoding="utf-8") == '{"kind":"note","text":"hej"}\n'
    assert path.stat().st_mode & 0o777 == 0o600


def test_read_day_uses_complete_lines_only(tmp_path: Path) -> None:
    path = tmp_path / "day.jsonl"
    path.write_bytes(b'{"a":1}\n{"b":2}\n{"c":3}')
    assert streams.read_day(path) == [{"a": 1}, {"b": 2}]


def test_read_missing_day_is_empty(tmp_path: Path) -> None:
    assert streams.read_day(tmp_path / "missing.jsonl") == []


def test_read_days_inclusive(tmp_path: Path) -> None:
    directory = tmp_path / "events"
    directory.mkdir()
    streams.append(streams.day_path(directory, date(2026, 11, 21)), {"day": 21})
    streams.append(streams.day_path(directory, date(2026, 11, 22)), {"day": 22})
    streams.append(streams.day_path(directory, date(2026, 11, 23)), {"day": 23})
    records = streams.read_days(directory, date(2026, 11, 22), date(2026, 11, 23))
    assert [record["day"] for record in records] == [22, 23]


@pytest.mark.looptime(False)
async def test_follow_new_lines(tmp_path: Path) -> None:
    path = tmp_path / "events" / "day.jsonl"
    records: list[dict[str, object]] = []

    async def consume() -> None:
        async for record in streams.follow(path, start_at_end=False, scan_s=0.05):
            records.append(record)
            if len(records) == 2:
                return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)
    streams.append(path, {"n": 1})
    streams.append(path, {"n": 2})
    await asyncio.wait_for(task, timeout=3)
    assert records == [{"n": 1}, {"n": 2}]


@pytest.mark.looptime(False)
async def test_follow_start_at_end_skips_old_lines(tmp_path: Path) -> None:
    path = tmp_path / "day.jsonl"
    streams.append(path, {"n": 1})
    records: list[dict[str, object]] = []

    async def consume() -> None:
        async for record in streams.follow(path, scan_s=0.05):
            records.append(record)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)
    streams.append(path, {"n": 2})
    await asyncio.wait_for(task, timeout=3)
    assert records == [{"n": 2}]


@pytest.mark.looptime(False)
async def test_follow_backstop_scan_finds_a_line(tmp_path: Path) -> None:
    path = tmp_path / "day.jsonl"
    records: list[dict[str, object]] = []

    async def consume() -> None:
        async for record in streams.follow(path, start_at_end=False, scan_s=0.05):
            records.append(record)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)
    path.write_text('{"n": 1}\n', encoding="utf-8")
    await asyncio.wait_for(task, timeout=3)
    assert records == [{"n": 1}]
