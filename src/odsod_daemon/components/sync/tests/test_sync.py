"""Sync from a satellite to the base through real rsync and a fake ssh."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.sync import plan, service
from odsod_daemon.components.sync.config import SyncConfig
from odsod_daemon.lib import clock, paths

BIN = Path(__file__).parents[5] / "tests/bin"


@pytest.fixture
def satellite(temp_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    inference = {
        "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
        "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
    }
    common = {
        "inference": inference,
        "role": "satellite",
        "base": "desktop",
        "host": "laptop",
    }
    (temp_root / "config/config.json").write_text(json.dumps({"common": common}))
    home = temp_root / "base-home"
    home.mkdir()
    monkeypatch.setenv("FAKE_SSH_HOME", str(home))
    monkeypatch.setenv("PATH", f"{BIN}{os.pathsep}{os.environ['PATH']}")
    return home


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(data)


def test_commands_send_dictation_before_audio(temp_root: Path) -> None:
    roots = paths.roots()
    write(roots.state / "audio/mic/20261125T12Z.pcm", b"a")
    write(roots.state / "utterances/dictation/2026-11-25.jsonl", b"{}\n")
    write(roots.run / "status.json", b"{}")
    commands = plan.commands(roots, "laptop", "desktop", "s")
    assert [c[-2] for c in commands] == [
        f"{roots.state}/./utterances/dictation",
        str(roots.run / "status.json"),
        f"{roots.state}/./audio",
    ]
    assert all(c[-1].startswith("desktop:s/hosts/laptop/") for c in commands)
    assert commands[1][-1] == "desktop:s/hosts/laptop/run/"


def test_commands_skip_missing_paths(temp_root: Path) -> None:
    assert plan.commands(paths.roots(), "laptop", "desktop", "s") == []


async def test_pass_copies_and_then_appends(satellite: Path) -> None:
    """ADR-0024: the host root on the base gets audio, events and the hold."""
    roots = paths.roots()
    hour = roots.state / "audio/mic/20261125T12Z.pcm"
    events = roots.state / "events/capture/2026-11-25.jsonl"
    write(hour, b"\x01\x00" * 1000)
    write(events, b'{"kind":"start"}\n')
    write(roots.run / "status.json", b'{"mode":"idle"}')
    settings = SyncConfig(remote_state="state")
    await service.run(settings, once=True)
    root = satellite / "state/hosts/laptop"
    assert (root / "audio/mic/20261125T12Z.pcm").read_bytes() == hour.read_bytes()
    assert (
        root / "events/capture/2026-11-25.jsonl"
    ).read_bytes() == events.read_bytes()
    assert (root / "run/status.json").read_bytes() == b'{"mode":"idle"}'
    write(hour, b"\x02\x00" * 500)
    write(events, b'{"kind":"stop"}\n')
    await service.run(settings, once=True)
    assert (root / "audio/mic/20261125T12Z.pcm").read_bytes() == hour.read_bytes()
    assert (
        root / "events/capture/2026-11-25.jsonl"
    ).read_bytes() == events.read_bytes()
    assert not (roots.run / "health/pipeline.json").exists()


async def test_unreachable_base_sets_and_clears_sync_behind(
    satellite: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = paths.roots()
    write(roots.state / "events/user/2026-11-25.jsonl", b"{}\n")
    monkeypatch.setenv("FAKE_SSH_DOWN", "1")
    settings = SyncConfig(remote_state="state", behind_after_s=0)
    await service.run(settings, once=True)
    health = json.loads((roots.run / "health/pipeline.json").read_text())
    assert [f["code"] for f in health["faults"]] == ["sync-behind"]
    monkeypatch.delenv("FAKE_SSH_DOWN")
    await service.run(settings, once=True)
    health = json.loads((roots.run / "health/pipeline.json").read_text())
    assert health["faults"] == []


async def test_base_role_does_nothing(temp_root: Path) -> None:
    inference = {
        "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
        "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
    }
    (temp_root / "config/config.json").write_text(
        json.dumps({"common": {"inference": inference}})
    )
    await service.run(SyncConfig(), once=True)
    assert not (temp_root / "run/health/pipeline.json").exists()


async def test_paused_sync_sends_nothing_and_is_no_fault(
    satellite: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0024: on mobile data, audio stays here until resume."""
    roots = paths.roots()
    write(roots.state / "audio/mic/20261125T12Z.pcm", b"\x01\x00" * 1000)
    runner = CliRunner()
    assert runner.invoke(app, ["sync", "pause"]).exit_code == 0
    again = runner.invoke(app, ["sync", "pause", "--json"])
    assert not json.loads(again.stdout)["changed"]
    monkeypatch.setenv("FAKE_SSH_DOWN", "1")
    await service.run(SyncConfig(remote_state="state", behind_after_s=0), once=True)
    assert not (satellite / "state/hosts").exists()
    assert not (roots.run / "health/pipeline.json").exists()
    monkeypatch.delenv("FAKE_SSH_DOWN")
    assert runner.invoke(app, ["sync", "resume"]).exit_code == 0
    await service.run(SyncConfig(remote_state="state"), once=True)
    assert (satellite / "state/hosts/laptop/audio/mic/20261125T12Z.pcm").exists()


async def test_pause_stops_a_running_transfer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "POLL_S", 0.05)
    flags = iter([False, False, True])
    started = clock.monotonic()
    result = await service.run_pass([["sleep", "30"]], lambda: next(flags, True))
    assert result == service.PAUSED
    assert clock.monotonic() - started < 5


def test_sync_commands_refuse_a_base(temp_root: Path) -> None:
    inference = {
        "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
        "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
    }
    (temp_root / "config/config.json").write_text(
        json.dumps({"common": {"inference": inference}})
    )
    result = CliRunner().invoke(app, ["sync", "pause"])
    assert result.exit_code == 1
    assert "not a satellite" in result.stderr
