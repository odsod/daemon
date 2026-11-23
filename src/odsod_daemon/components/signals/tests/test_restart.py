from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from odsod_daemon.components.signals.collector import Collector
from odsod_daemon.components.signals.config import SignalsConfig
from odsod_daemon.components.signals.contract import (
    MeetingStart,
    Participants,
    Speaking,
)
from odsod_daemon.lib import clock, paths, streams

pytestmark = pytest.mark.looptime(False)

MEET_URL = "https://meet.google.com/abc-defg-hij"
OTHER_URL = "https://meet.google.com/zzz-yyyy-xxx"


def snapshot(*tiles: tuple[str, list[str]]) -> str:
    return json.dumps([{"name": name, "classes": classes} for name, classes in tiles])


def poll(*tiles: tuple[str, bool]) -> str:
    return json.dumps(
        [{"name": name, "speaking": speaking} for name, speaking in tiles]
    )


def records(root: Path) -> list[dict[str, Any]]:
    day: date = clock.utc_now().date()
    return streams.read_days(root / "state" / "events" / "signals", day, day)


def write_open_meeting(
    root: Path, *, code: str = "abc-defg-hij", day_offset: int = 0
) -> None:
    directory = root / "state" / "events" / "signals"
    day = clock.utc_now().date() - timedelta(days=day_offset)
    path = streams.day_path(directory, day)
    at = clock.iso(datetime.fromtimestamp(clock.wall() - 60, UTC))
    url = f"https://meet.google.com/{code}"
    for record in (
        MeetingStart(
            ts=clock.iso(), platform="meet", code=code, title="Standup", url=url, at=at
        ),
        Participants(ts=clock.iso(), platform="meet", code=code, names=["Alice"]),
        Speaking(ts=clock.iso(), platform="meet", code=code, names=["Bob"], at=at),
    ):
        streams.append(path, record.model_dump(mode="json"))


def collector(fake: Any) -> Collector:
    config = SignalsConfig(cdp_ports=[fake.port])
    return Collector(config, roots=paths.roots())


async def test_same_meeting_continues_without_a_new_start(
    fake_cdp: Any, temp_root: Path
) -> None:
    write_open_meeting(temp_root)
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[snapshot(("Alice", ["cls-a"]))])
    signals = collector(fake_cdp)
    start = clock.wall()
    before = records(temp_root)
    await signals.start(start)
    await signals.tab_tick(start)
    assert records(temp_root) == before

    fake_cdp.script(polls=[poll(("Alice", False), ("Bob", True))])
    await signals.speaking_tick(start + 0.25)
    await signals.speaking_tick(start + 0.5)
    assert records(temp_root) == before


async def test_adopted_speaker_stops_after_the_grace(
    fake_cdp: Any, temp_root: Path
) -> None:
    write_open_meeting(temp_root)
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    base = snapshot(("Alice", ["cls-a"]))
    fake_cdp.script(snapshots=[base, snapshot(("Alice", ["cls-a", "x"])), base])
    config = SignalsConfig(cdp_ports=[fake_cdp.port], toggles_required=1)
    signals = Collector(config, roots=paths.roots())
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 2, 4):
        await signals.tab_tick(start + offset)

    fake_cdp.script(polls=[poll(("Alice", False), ("Bob", False))])
    await signals.speaking_tick(start + 4.25)

    speaking = [r for r in records(temp_root) if r["kind"] == "speaking"]
    assert speaking[-1]["names"] == []
    assert speaking[-1]["at"] == clock.iso(datetime.fromtimestamp(start + 0.25, UTC))


async def test_gone_meeting_ends_with_restart(fake_cdp: Any, temp_root: Path) -> None:
    write_open_meeting(temp_root)
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    await signals.tab_tick(start)

    written = records(temp_root)
    assert [record["kind"] for record in written][-2:] == ["speaking", "meeting-end"]
    assert written[-2]["names"] == []
    assert written[-1]["cause"] == "restart"
    assert written[-1]["at"] == clock.iso(datetime.fromtimestamp(start, UTC))
    assert [r["kind"] for r in written].count("meeting-start") == 1


async def test_open_meeting_from_yesterday_is_found(
    fake_cdp: Any, temp_root: Path
) -> None:
    write_open_meeting(temp_root, day_offset=1)
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    await signals.tab_tick(start)
    written = records(temp_root)
    assert [record["kind"] for record in written][-2:] == ["speaking", "meeting-end"]
    assert written[-1]["cause"] == "restart"


async def test_a_different_meeting_at_start_is_ended_and_started(
    fake_cdp: Any, temp_root: Path
) -> None:
    write_open_meeting(temp_root)
    fake_cdp.add_tab("Meet \u2013 Review", OTHER_URL)
    fake_cdp.script(snapshots=[snapshot(("Carol", ["cls-a"]))])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    await signals.tab_tick(start)

    written = records(temp_root)
    assert [record["kind"] for record in written][-3:] == [
        "speaking",
        "meeting-end",
        "meeting-start",
    ]
    assert written[-2]["code"] == "abc-defg-hij"
    assert written[-2]["cause"] == "restart"
    assert written[-1]["code"] == "zzz-yyyy-xxx"
