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


@pytest.mark.looptime(False)
async def test_idle_followers_start_no_threads(tmp_path: Path) -> None:
    """A follower waits on inotify in the event loop. Polling threads woke
    every 10 ms each and cost the laptop 12% of a core (2026-11-25)."""
    import threading

    async def consume(path: Path) -> None:
        async for _ in streams.follow(path):
            pass

    before = threading.active_count()
    tasks = [
        asyncio.create_task(consume(tmp_path / f"d{n}" / "day.jsonl"))
        for n in range(10)
    ]
    await asyncio.sleep(0.3)
    try:
        assert threading.active_count() - before < 2
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_read_day_parses_only_new_lines(tmp_path: Path, monkeypatch) -> None:
    """Services re-read whole day files about 30 times a second. Parsing them
    again cost the laptop 18% of a core on battery (2026-11-25)."""
    import json

    path = tmp_path / "day.jsonl"
    for n in range(3):
        streams.append(path, {"n": n})
    assert streams.read_day(path) == [{"n": 0}, {"n": 1}, {"n": 2}]
    parsed = []
    loads = json.loads
    monkeypatch.setattr(
        streams.json, "loads", lambda raw: parsed.append(1) or loads(raw)
    )
    with path.open("ab") as handle:
        handle.write(b'{"n":3}\n{"n":')
    assert streams.read_day(path) == [{"n": 0}, {"n": 1}, {"n": 2}, {"n": 3}]
    assert len(parsed) == 1
    with path.open("ab") as handle:
        handle.write(b"4}\n")
    assert streams.read_day(path)[-1] == {"n": 4}
    streams.read_day(path)[0]["n"] = 99
    assert streams.read_day(path)[0] == {"n": 0}


def test_read_day_rereads_a_replaced_file(tmp_path: Path) -> None:
    path = tmp_path / "day.jsonl"
    streams.append(path, {"n": 0})
    streams.append(path, {"n": 1})
    assert len(streams.read_day(path)) == 2
    path.unlink()
    assert streams.read_day(path) == []
    streams.append(path, {"n": 2})
    assert streams.read_day(path) == [{"n": 2}]
