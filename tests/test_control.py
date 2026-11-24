"""Install and control through real files, a capture stub and fake systemd."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.install import apply as installer
from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.lib import audio, clock, documents, systemd


class FileUnitStates:
    """The read side of tests/bin/systemctl, without a real D-Bus manager."""

    def __init__(self, root: Path):
        self.root = root

    async def get(self, unit: str, *, scope: str = "user") -> systemd.UnitState:
        path = self.root / "systemctl.json"
        states = json.loads(path.read_text()) if path.exists() else {}
        active = states.get(
            unit, "active" if unit == "graphical-session.target" else "inactive"
        )
        return systemd.UnitState(
            unit,
            scope,
            active,
            "running" if active == "active" else "dead",
            "success",
            0,
        )

    async def close(self):
        pass


class CaptureStub:
    """Write hourly audio while fake systemd marks capture active."""

    def __init__(self, root: Path):
        self.root = root
        self.stop = threading.Event()
        self.wrote = threading.Event()
        self.paused = threading.Event()
        self.thread = threading.Thread(target=self.run)

    def run(self):
        while not self.stop.wait(0.02):
            path = self.root / "systemctl.json"
            states = json.loads(path.read_text()) if path.exists() else {}
            if states.get("odsod-daemon-capture.service") != "active":
                self.paused.set()
                continue
            self.paused.clear()
            now = clock.utc_now()
            for channel in ("mic", "sys"):
                file = audio.hour_file(self.root / "state", channel, now)
                file.parent.mkdir(parents=True, exist_ok=True)
                offset = int(
                    (now - audio.hour_start(now)).total_seconds()
                    * audio.BYTES_PER_SECOND
                )
                with file.open("ab") as handle:
                    handle.truncate(offset)
            self.wrote.set()

    def sizes(self):
        return {
            str(p): p.stat().st_size for p in (self.root / "state/audio").rglob("*.pcm")
        }


@pytest.fixture
def control(fake_control, monkeypatch):
    root = fake_control
    documents.write_json(
        root / "config/config.json",
        {
            "common": {
                "inference": {
                    "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
                    "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
                }
            },
            # Coverage is outside this stub's job.
            "control": {"backlog_warning_s": 100_000},
        },
    )
    monkeypatch.setattr(
        "odsod_daemon.components.status.cli.systemd.DBusUnitStates",
        lambda: FileUnitStates(root),
    )
    return root


def deploy(commit="a", source: Literal["git", "dev"] = "git"):
    """Each commit installs its own code, so a new commit restarts all."""
    package = Path(os.environ["ODSOD_DAEMON_ROOT"]).parent / f"package-{commit}"
    (package / "components/capture").mkdir(parents=True, exist_ok=True)
    (package / "components/capture/channel.py").write_text(commit)
    installer.install_user(
        command=Path("/usr/bin/true"),
        package=package,
        candidate=InstallRecord(
            source=source,
            commit=commit,
            workspace="/tmp/work" if source == "dev" else None,
            installed_at=clock.iso(),
        ),
    )


def status():
    result = CliRunner().invoke(app, ["status", "--json"])
    return result, json.loads(result.stdout)


def test_control_pause_status_resume(control):
    root = control
    deploy(source="dev")
    stub = CaptureStub(root)
    stub.thread.start()
    try:
        assert stub.wrote.wait(5)
        result, report = status()
        assert result.exit_code == 0, report
        assert report["state"] == "running"
        assert report["dev"]
        assert CliRunner().invoke(app, ["pause"]).exit_code == 0
        assert stub.paused.wait(5)
        paused_sizes = stub.sizes()
        assert status()[1]["state"] == "paused"
        assert stub.sizes() == paused_sizes
        stub.wrote.clear()
        assert CliRunner().invoke(app, ["resume"]).exit_code == 0
        assert stub.wrote.wait(5)
        assert stub.sizes() != paused_sizes
        assert status()[1]["state"] == "running"
    finally:
        stub.stop.set()
        stub.thread.join(timeout=5)
        assert not stub.thread.is_alive()


def test_install_preserves_pause_and_owner_data(control):
    root = control
    documents.write_json(root / "run/paused", {"since": clock.iso()})
    documents.write(root / "state/owner.txt", "keep")
    before = {p: p.read_bytes() for p in (root / "config").rglob("*") if p.is_file()}
    deploy()
    states = json.loads((root / "systemctl.json").read_text())
    assert states["odsod-daemon-capture.service"] == "inactive"
    assert status()[1]["state"] == "paused"
    assert {p: p.read_bytes() for p in before} == before
    assert {
        str(p.relative_to(root / "state"))
        for p in (root / "state").rglob("*")
        if p.is_file()
    } == {"owner.txt", "install/current"}
    assert (root / "state/owner.txt").read_text() == "keep"


@pytest.mark.parametrize("step", [3, 6])
def test_install_failure_retries_all_services(control, monkeypatch, step):
    root = control
    deploy()
    current = (root / "state/install/current").read_bytes()
    with monkeypatch.context() as injected:
        if step == 3:
            unit = (
                Path(os.environ["XDG_CONFIG_HOME"])
                / "systemd/user/odsod-daemon-pipeline.service"
            )
            unit.write_text("old template")
            original = documents.write

            def fail(path, content):
                if path == unit:
                    raise OSError("injected write failure")
                original(path, content)

            injected.setattr(installer.documents, "write", fail)
        else:
            injected.setenv(
                "FAKE_SYSTEMCTL_FAIL", "restart odsod-daemon-pipeline.service"
            )
        with pytest.raises(installer.ApplyError, match=f"failed at step {step}"):
            deploy("b")
        assert (root / "state/install/current").read_bytes() == current
    (root / "systemctl.log").unlink()
    deploy("b")
    calls = (root / "systemctl.log").read_text()
    assert "restart odsod-daemon-capture.service" in calls
    assert "restart odsod-daemon-pipeline.service" in calls
    assert documents.read_json(root / "state/install/current")["commit"] == "b"


@pytest.mark.timing
def test_control_status_fourteen_day_backlog_under_one_second(control):
    import time
    from datetime import timedelta

    root = control
    now = clock.utc_now()
    documents.write_json(
        root / "systemctl.json",
        {
            "graphical-session.target": "inactive",
            "odsod-daemon-pipeline.service": "active",
        },
    )
    for day in range(14):
        at = now - timedelta(days=day, seconds=20)
        directory = root / "state/utterances/ambient"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{at.date().isoformat()}.jsonl"
        with path.open("w") as handle:
            for i in range(10_000):
                handle.write(
                    json.dumps(
                        {
                            "id": f"{day}-{i}",
                            "start": clock.iso(at),
                            "end": clock.iso(at + timedelta(seconds=1)),
                        }
                    )
                    + "\n"
                )
    started = time.monotonic()
    result, report = status()
    elapsed = time.monotonic() - started
    assert result.exit_code == 1, report
    assert report["backlog"]["count"] == 140_000
    assert elapsed < 1, f"status took {elapsed:.3f}s"
