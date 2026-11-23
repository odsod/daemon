from __future__ import annotations

import json
import socket
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from odsod_daemon.components import signals
from odsod_daemon.components.signals.collector import Collector
from odsod_daemon.components.signals.config import SignalsConfig
from odsod_daemon.lib import clock, paths, streams

MEET_URL = "https://meet.google.com/abc-defg-hij"
OTHER_URL = "https://meet.google.com/zzz-yyyy-xxx"

pytestmark = pytest.mark.looptime(False)


def snapshot(*tiles: tuple[str, list[str]]) -> str:
    return json.dumps([{"name": name, "classes": classes} for name, classes in tiles])


def poll(*tiles: tuple[str, bool]) -> str:
    return json.dumps(
        [{"name": name, "speaking": speaking} for name, speaking in tiles]
    )


def config(fake: Any, **overrides: Any) -> SignalsConfig:
    return SignalsConfig(cdp_ports=[fake.port], **overrides)


def records(root: Path) -> list[dict[str, Any]]:
    day: date = clock.utc_now().date()
    return streams.read_days(root / "state" / "events" / "signals", day, day)


def kinds(root: Path) -> list[str]:
    return [str(record["kind"]) for record in records(root)]


async def test_scripted_meeting_writes_one_record_per_change(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a", "cls-b"]), ("Bob Jones", ["cls-a"])),
        snapshot(("Alice Smith", ["cls-a", "cls-b", "x"]), ("Bob Jones", ["cls-a"])),
        snapshot(("Alice Smith", ["cls-a", "cls-b"]), ("Bob Jones", ["cls-a"])),
        snapshot(("Alice Smith", ["cls-a", "cls-b", "x"]), ("Bob Jones", ["cls-a"])),
        snapshot(("Alice Smith", ["cls-a", "cls-b"]), ("Bob Jones", ["cls-a"])),
    ]
    collector = Collector(config(fake_cdp), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    for offset in (0, 2, 4, 6, 8):
        await collector.tab_tick(start + offset)

    fake_cdp.poll_values = [
        poll(("Alice Smith", False), ("Bob Jones", True)),
    ]
    await collector.speaking_tick(start + 8.25)
    await collector.speaking_tick(start + 8.5)
    fake_cdp.poll_values = [
        poll(("Alice Smith", False), ("Bob Jones", False)),
    ]
    await collector.speaking_tick(start + 8.75)
    await collector.speaking_tick(start + 10.75)

    written = records(temp_root)
    assert [record["kind"] for record in written] == [
        "meeting-start",
        "participants",
        "speaking",
        "speaking",
    ]

    meeting = written[0]
    assert meeting["platform"] == "meet"
    assert meeting["code"] == "abc-defg-hij"
    assert meeting["title"] == "Standup"
    assert meeting["url"] == MEET_URL
    assert meeting["at"] == clock.iso(datetime.fromtimestamp(start, UTC))

    assert written[1]["names"] == ["Alice Smith", "Bob Jones"]
    assert written[2]["names"] == ["Bob Jones"]
    assert written[3]["names"] == []


async def test_speaking_times_follow_the_debounce(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"]), ("Bob Jones", ["cls-a"]))
    ]
    collector = Collector(config(fake_cdp, toggles_required=1), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a", "x"]), ("Bob Jones", ["cls-a"]))
    ]
    await collector.tab_tick(start)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"]), ("Bob Jones", ["cls-a"]))
    ]
    await collector.tab_tick(start + 2)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a", "x"]), ("Bob Jones", ["cls-a"]))
    ]
    await collector.tab_tick(start + 4)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"]), ("Bob Jones", ["cls-a"]))
    ]
    await collector.tab_tick(start + 6)

    fake_cdp.poll_values = [
        poll(("Alice Smith", True), ("Bob Jones", False)),
    ]
    await collector.speaking_tick(start + 6.25)
    await collector.speaking_tick(start + 6.5)

    speaking = [record for record in records(temp_root) if record["kind"] == "speaking"]
    assert len(speaking) == 1
    assert speaking[0]["names"] == ["Alice Smith"]
    assert speaking[0]["at"] == clock.iso(datetime.fromtimestamp(start + 6.25, UTC))


async def test_lobby_waits_for_a_participant_tile(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = ["[]"]
    collector = Collector(config(fake_cdp), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    await collector.tab_tick(start)
    assert records(temp_root) == []

    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"]), ("Bob Jones", ["cls-a"]))
    ]
    await collector.tab_tick(start + 2)
    assert kinds(temp_root) == ["meeting-start"]


async def test_tab_closed_clears_speaking_then_ends(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"])),
        snapshot(("Alice Smith", ["cls-a", "x"])),
        snapshot(("Alice Smith", ["cls-a"])),
    ]
    collector = Collector(config(fake_cdp, toggles_required=1), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    for offset in (0, 2, 4):
        await collector.tab_tick(start + offset)
    fake_cdp.poll_values = [poll(("Alice Smith", True))]
    await collector.speaking_tick(start + 4.25)
    await collector.speaking_tick(start + 4.5)

    fake_cdp.tabs.clear()
    await collector.tab_tick(start + 6)

    written = records(temp_root)
    assert [record["kind"] for record in written][-2:] == ["speaking", "meeting-end"]
    assert written[-2]["names"] == []
    assert written[-1]["cause"] == "tab-closed"


async def test_code_change_ends_and_starts(fake_cdp: Any, temp_root: Path) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = [snapshot(("Alice Smith", ["cls-a"]))]
    collector = Collector(config(fake_cdp), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    await collector.tab_tick(start)

    fake_cdp.tabs.clear()
    fake_cdp.add_tab("Meet \u2013 Review", OTHER_URL)
    await collector.tab_tick(start + 2)

    written = records(temp_root)
    assert [record["kind"] for record in written] == [
        "meeting-start",
        "meeting-end",
        "meeting-start",
    ]
    assert written[1]["code"] == "abc-defg-hij"
    assert written[1]["cause"] == "tab-closed"
    assert written[2]["code"] == "zzz-yyyy-xxx"


async def test_a_dropped_socket_reconnects(fake_cdp: Any, temp_root: Path) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.snapshot_values = [
        snapshot(("Alice Smith", ["cls-a"]), ("Bob Jones", ["cls-a"]))
    ]
    collector = Collector(config(fake_cdp), roots=paths.roots())
    start = clock.wall()
    await collector.start(start)
    await collector.tab_tick(start)

    fake_cdp.drop_next = 1
    await collector.speaking_tick(start + 0.25)
    assert len(records(temp_root)) == 1

    await collector.tab_tick(start + 2)
    assert len(records(temp_root)) == 1


async def test_no_debug_port_is_not_a_fault(temp_root: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    collector = Collector(SignalsConfig(cdp_ports=[port]), roots=paths.roots())
    await collector.run(once=True)
    assert records(temp_root) == []


async def test_empty_ports_turn_signals_off(temp_root: Path) -> None:
    await signals.run(SignalsConfig(cdp_ports=[]), once=True)
    assert records(temp_root) == []
