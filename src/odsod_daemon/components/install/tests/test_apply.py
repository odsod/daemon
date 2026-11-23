import json
import os
from pathlib import Path

import pytest

from odsod_daemon.components.install.apply import ApplyError, install_user
from odsod_daemon.components.install.contract import InstallRecord, Source
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


def record(commit="a", source: Source = "git"):
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


@pytest.mark.parametrize("graphical", [True, False])
def test_future_graphical_services_use_the_right_restart(
    installed, monkeypatch, graphical
):
    from odsod_daemon.components.install import apply as apply_module
    from odsod_daemon.components.install import render as render_module

    services = ("capture", "pipeline", "session", "tray")
    monkeypatch.setattr(apply_module, "SERVICES", services)
    monkeypatch.setattr(render_module, "SERVICES", services)
    installed.mkdir()
    documents.write_json(
        installed / "systemctl.json",
        {
            "graphical-session.target": "active" if graphical else "inactive",
        },
    )
    apply(record())
    log = calls(installed)
    for name in ("capture", "session", "tray"):
        assert f"enable odsod-daemon-{name}.service" in log
        action = "restart" if graphical else "try-restart"
        assert f"{action} odsod-daemon-{name}.service" in log
        assert (f"start odsod-daemon-{name}.service" in log) == graphical
    assert "enable odsod-daemon-login.service" in log


def test_only_changed_service_restarts(installed, monkeypatch):
    apply(record())
    unit = (
        Path(os.environ["XDG_CONFIG_HOME"])
        / "systemd/user/odsod-daemon-pipeline.service"
    )
    unit.write_text("old")
    (installed / "systemctl.log").unlink()
    apply(record())
    log = calls(installed)
    assert "daemon-reload" in log
    assert "restart odsod-daemon-pipeline.service" in log
    assert "restart odsod-daemon-capture.service" not in log
