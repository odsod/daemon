from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from odsod_daemon.components.signals.collector import Collector
from odsod_daemon.components.signals.config import SignalsConfig
from odsod_daemon.lib import clock, documents, healthfile, paths

pytestmark = pytest.mark.looptime(False)

MEET_URL = "https://meet.google.com/abc-defg-hij"
TWO = json.dumps(
    [
        {"name": "Alice Smith", "classes": ["cls-a"]},
        {"name": "Bob Jones", "classes": ["cls-a"]},
    ]
)
WITH_X = json.dumps(
    [
        {"name": "Alice Smith", "classes": ["cls-a", "x"]},
        {"name": "Bob Jones", "classes": ["cls-a"]},
    ]
)
SPEAKING = json.dumps(
    [
        {"name": "Alice Smith", "speaking": True},
        {"name": "Bob Jones", "speaking": False},
    ]
)
ALONE = json.dumps([{"name": "Alice Smith", "speaking": False}])
BOTH = json.dumps(
    [
        {"name": "Alice Smith", "speaking": False},
        {"name": "Bob Jones", "speaking": False},
    ]
)


def health(temp_root: Path) -> dict[str, Any]:
    return documents.read_json(temp_root / "run" / "health" / "pipeline.json")


def faults(temp_root: Path) -> list[dict[str, Any]]:
    path = temp_root / "run" / "health" / "pipeline.json"
    if not path.exists():
        return []
    return list(documents.read_json(path)["faults"])


def collector(fake: Any) -> Collector:
    config = SignalsConfig(
        cdp_ports=[fake.port], toggles_required=1, no_indicator_after_s=300
    )
    return Collector(config, roots=paths.roots())


async def test_no_speaking_indicator_reports_a_fault(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[TWO])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 150, 301):
        await signals.tab_tick(start + offset)

    document = health(temp_root)
    assert document["service"] == "pipeline"
    assert [fault["code"] for fault in document["faults"]] == ["no-speaking-indicator"]
    fault = document["faults"][0]
    assert "`meet`" in fault["message"]
    assert "5 min" in fault["message"]
    assert fault["fix"] is None


async def test_a_confirmed_speaker_clears_the_fault(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[TWO])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 301):
        await signals.tab_tick(start + offset)
    assert health(temp_root)["faults"]

    fake_cdp.script(snapshots=[WITH_X, TWO])
    await signals.tab_tick(start + 302)
    await signals.tab_tick(start + 304)
    assert health(temp_root)["faults"]

    fake_cdp.script(polls=[SPEAKING])
    await signals.speaking_tick(start + 304.25)
    await signals.speaking_tick(start + 304.5)
    assert health(temp_root)["faults"] == []


async def test_waiting_alone_then_a_join_gives_no_immediate_fault(
    fake_cdp: Any, temp_root: Path
) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[TWO, WITH_X, TWO])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 2, 4):
        await signals.tab_tick(start + offset)
    assert faults(temp_root) == []

    fake_cdp.script(polls=[ALONE, BOTH])
    await signals.tab_tick(start + 304)
    assert faults(temp_root) == []

    await signals.tab_tick(start + 306)
    assert faults(temp_root) == []


async def test_meeting_end_clears_the_fault(fake_cdp: Any, temp_root: Path) -> None:
    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[TWO])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 301):
        await signals.tab_tick(start + offset)
    assert health(temp_root)["faults"]

    fake_cdp.tabs.clear()
    await signals.tab_tick(start + 302)
    assert health(temp_root)["faults"] == []


async def test_the_fault_file_keeps_other_faults(
    fake_cdp: Any, temp_root: Path
) -> None:
    path = temp_root / "run" / "health" / "pipeline.json"
    other = healthfile.HealthFile(path, "pipeline")
    other.set("inference-unreachable", "down", key="whisper")
    other.rewrite()

    fake_cdp.add_tab("Meet \u2013 Standup", MEET_URL)
    fake_cdp.script(snapshots=[TWO])
    signals = collector(fake_cdp)
    start = clock.wall()
    await signals.start(start)
    for offset in (0, 301):
        await signals.tab_tick(start + offset)

    assert [fault["code"] for fault in health(temp_root)["faults"]] == [
        "inference-unreachable",
        "no-speaking-indicator",
    ]
