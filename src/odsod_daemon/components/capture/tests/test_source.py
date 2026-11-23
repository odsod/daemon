"""The pactl client against the fake script on PATH."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from odsod_daemon.components.capture import source

BIN = Path(__file__).parent / "bin"


@pytest.fixture
def fake_pactl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([{"name": "fake_mic", "mute": False}]))
    monkeypatch.setenv("PATH", f"{BIN}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_PACTL_SOURCES", str(sources))
    monkeypatch.setenv("FAKE_PACTL_LOG", str(tmp_path / "pactl.log"))
    return sources


@pytest.mark.looptime(False)
async def test_read_default_reports_the_mute_flag(fake_pactl: Path) -> None:
    assert await source.read_default() == source.SourceState(
        name="fake_mic", muted=False
    )
    fake_pactl.write_text(json.dumps([{"name": "fake_mic", "mute": True}]))
    assert (await source.read_default()).muted is True


@pytest.mark.looptime(False)
async def test_read_default_without_a_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", f"{BIN}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_PACTL_DEFAULT", "")
    monkeypatch.setenv("FAKE_PACTL_SOURCES", "[]")
    assert await source.read_default() == source.SourceState(name=None, muted=False)


@pytest.mark.looptime(False)
async def test_watch_reports_the_new_mute_after_a_source_event(
    fake_pactl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_PACTL_EVENTS", json.dumps(["Event 'change' on source #1"]))
    monkeypatch.setenv("FAKE_PACTL_EVENT_DELAY", "0.3")
    seen: list[source.SourceState] = []

    def on_state(state: source.SourceState) -> None:
        seen.append(state)

    stopping = asyncio.Event()
    task = asyncio.create_task(source.watch(on_state, stopping))
    try:
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.05)
        fake_pactl.write_text(json.dumps([{"name": "fake_mic", "mute": True}]))
        for _ in range(100):
            if any(state.muted for state in seen):
                break
            await asyncio.sleep(0.05)
    finally:
        stopping.set()
        await asyncio.wait_for(task, 5)
    assert seen[0].muted is False
    assert any(state.muted for state in seen)
