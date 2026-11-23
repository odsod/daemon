import json
import os
from pathlib import Path

import pytest

from odsod_daemon.components.install.apply import ApplyError, install_user
from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.lib import documents

BIN = Path(__file__).resolve().parents[5] / "tests/bin"


@pytest.fixture
def installed(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home/.config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home/.local/share"))
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("PATH", f"{BIN}:{os.environ['PATH']}")
    return tmp_path / "root"


def record(commit="a", source="git"):
    return InstallRecord(source=source, commit=commit, installed_at="now")


def apply(candidate):
    install_user(command=Path("/usr/bin/true"), candidate=candidate)


def calls(root):
    return (root / "systemctl.log").read_text().splitlines()


def test_idempotent_and_commit_change(installed):
    apply(record())
    current = installed / "state/install/current"
    stamp = current.stat().st_mtime_ns
    (installed / "systemctl.log").unlink()
    apply(record())
    assert not any(
        c.startswith(("restart ", "daemon-reload")) for c in calls(installed)
    )
    assert current.stat().st_mtime_ns == stamp
    apply(record("b"))
    previous = documents.read_json(installed / "state/install/previous-commit")
    assert previous["commit"] == "a"
    assert "restart odsod-daemon-capture.service" in calls(installed)
    assert "restart odsod-daemon-pipeline.service" in calls(installed)


def test_dev_always_restarts(installed):
    apply(record(source="dev"))
    (installed / "systemctl.log").unlink()
    apply(record(source="dev"))
    assert "restart odsod-daemon-capture.service" in calls(installed)
    assert "restart odsod-daemon-pipeline.service" in calls(installed)


def test_logged_out(installed):
    installed.mkdir()
    (installed / "systemctl.json").write_text(
        json.dumps({"graphical-session.target": "inactive"})
    )
    apply(record())
    assert "try-restart odsod-daemon-capture.service" in calls(installed)
    assert "start odsod-daemon-capture.service" not in calls(installed)


def test_failure_names_step_and_keeps_record(installed, monkeypatch):
    apply(record())
    monkeypatch.setenv("FAKE_SYSTEMCTL_FAIL", "restart odsod-daemon-pipeline.service")
    with pytest.raises(ApplyError, match=r"failed at step 6.*Restart"):
        apply(record("b"))
    assert documents.read_json(installed / "state/install/current")["commit"] == "a"
    monkeypatch.delenv("FAKE_SYSTEMCTL_FAIL")
    (installed / "systemctl.log").unlink()
    apply(record("b"))
    assert "restart odsod-daemon-capture.service" in calls(installed)
    assert "restart odsod-daemon-pipeline.service" in calls(installed)
