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
    pkg = tmp_path / "package"
    edit(pkg / "components/capture/channel.py", "from odsod_daemon.lib import audio")
    for name in ("components/cleanup/guard.py", "lib/audio.py", "lib/glossary.py"):
        edit(pkg / name, "v1")
    return tmp_path / "root"


def edit(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def record(commit="a", source: Source = "git"):
    return InstallRecord(source=source, commit=commit, installed_at="now")


def apply(candidate):
    package = Path(os.environ["ODSOD_DAEMON_ROOT"]).parent / "package"
    install_user(command=Path("/usr/bin/true"), candidate=candidate, package=package)


def package(root: Path) -> Path:
    return root.parent / "package"


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
    edit(package(installed) / "components/capture/channel.py", "import os")
    apply(record("b"))
    previous = documents.read_json(installed / "state/install/previous-commit")
    assert previous["commit"] == "a"
    assert "restart odsod-daemon-capture.service" in calls(installed)
    assert "restart odsod-daemon-pipeline.service" in calls(installed)


def test_commit_without_code_change_restarts_nothing(installed):
    apply(record())
    (installed / "systemctl.log").unlink()
    apply(record("b"))
    assert not any(c.startswith("restart ") for c in calls(installed))
    assert documents.read_json(installed / "state/install/current")["commit"] == "b"


def test_hot_deploy_keeps_capture_recording(installed):
    """PRD install-and-upgrade AC-16: no capture restart, no gap."""
    apply(record(source="dev"))
    (installed / "systemctl.log").unlink()
    edit(package(installed) / "components/cleanup/guard.py", "v2")
    apply(record(source="dev"))
    log = calls(installed)
    assert "restart odsod-daemon-pipeline.service" in log
    assert "restart odsod-daemon-tray.service" in log
    assert "restart odsod-daemon-capture.service" not in log


@pytest.mark.parametrize(
    "name", ["components/capture/x.py", "lib/audio.py", "services/runner.py"]
)
def test_capture_scope_change_restarts_capture(installed, name):
    apply(record(source="dev"))
    (installed / "systemctl.log").unlink()
    edit(package(installed) / name, "v2")
    apply(record(source="dev"))
    assert "restart odsod-daemon-capture.service" in calls(installed)


def test_lib_module_capture_does_not_import_keeps_capture(installed):
    apply(record(source="dev"))
    (installed / "systemctl.log").unlink()
    edit(package(installed) / "lib/glossary.py", "v2")
    apply(record(source="dev"))
    assert "restart odsod-daemon-capture.service" not in calls(installed)
    assert "restart odsod-daemon-pipeline.service" in calls(installed)


def test_capture_files_follow_imports():
    from odsod_daemon.components.install.apply import capture_files

    package = Path(__file__).resolve().parents[3]
    files = capture_files(package)
    assert {"components/capture/service.py", "lib/audio.py"} <= files
    assert "lib/textmatch.py" not in files
    assert not any(f.startswith("components/cleanup/") for f in files)


def test_record_without_digests_restarts_all(installed):
    apply(record())
    current = installed / "state/install/current"
    old = documents.read_json(current)
    del old["digests"]
    documents.write_json(current, old)
    (installed / "systemctl.log").unlink()
    apply(record())
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
    edit(package(installed) / "components/capture/channel.py", "import os")
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


def test_digests_skip_files_the_wheel_leaves_out(tmp_path):
    from odsod_daemon.components.install.apply import digests

    edit(tmp_path / "lib/audio.py", "code")
    before = digests(tmp_path)
    edit(tmp_path / "lib/tests/test_audio.py", "test")
    edit(tmp_path / "lib/inference/testdata/reply.json", "{}")
    edit(tmp_path / "lib/__pycache__/audio.pyc", "bytes")
    assert digests(tmp_path) == before


SERVER_UNITS = ("odsod-daemon-whisper.service", "odsod-daemon-llama.service")


def set_up_servers(root: Path, enabled: bool = True) -> None:
    from odsod_daemon.components.servers.contract import SERVERS

    documents.write_json(
        root / "config/config.json", {"inference": {"enabled": enabled}}
    )
    for server in SERVERS:
        edit(root / "state" / server.binary, f"{server.name} v1")
        edit(root / "state" / server.model, "weights")


def unit_file(name: str) -> Path:
    return Path(os.environ["XDG_CONFIG_HOME"]) / "systemd/user" / name


def test_server_units_only_on_an_enabled_set_up_host(installed):
    apply(record())
    assert not any(unit_file(name).exists() for name in SERVER_UNITS)
    set_up_servers(installed, enabled=False)
    apply(record())
    assert not any(unit_file(name).exists() for name in SERVER_UNITS)
    set_up_servers(installed)
    apply(record())
    log = calls(installed)
    for name in SERVER_UNITS:
        assert unit_file(name).exists()
        assert f"enable {name}" in log
        assert f"restart {name}" in log
    # Disabling inference removes the units and stops the servers.
    set_up_servers(installed, enabled=False)
    (installed / "systemctl.log").unlink()
    apply(record())
    assert not any(unit_file(name).exists() for name in SERVER_UNITS)
    for name in SERVER_UNITS:
        assert f"disable --now {name}" in calls(installed)


def test_enabled_without_setup_renders_no_server(installed):
    set_up_servers(installed)
    (installed / "state/models/ggml-large-v3.bin").unlink()
    lines: list[str] = []
    package = installed.parent / "package"
    install_user(
        command=Path("/usr/bin/true"),
        candidate=record(),
        package=package,
        progress=lines.append,
    )
    assert not any(unit_file(name).exists() for name in SERVER_UNITS)
    assert any("odsodctl inference setup" in line for line in lines)


def test_deploy_without_server_change_restarts_no_server(installed):
    """PRD install-and-upgrade: a deploy restarts no server unless it changed."""
    set_up_servers(installed)
    apply(record(source="dev"))
    (installed / "systemctl.log").unlink()
    edit(package(installed) / "components/cleanup/guard.py", "v2")
    apply(record(source="dev"))
    log = calls(installed)
    assert "restart odsod-daemon-pipeline.service" in log
    assert not any(f"restart {name}" in log for name in SERVER_UNITS)


def test_server_restarts_on_its_binary_or_unit_change(installed):
    from odsod_daemon.components.servers.contract import SERVERS

    set_up_servers(installed)
    apply(record())
    (installed / "systemctl.log").unlink()
    whisper = next(s for s in SERVERS if s.name == "whisper")
    edit(installed / "state" / whisper.binary, "whisper v2")
    apply(record())
    log = calls(installed)
    assert "restart odsod-daemon-whisper.service" in log
    assert "restart odsod-daemon-llama.service" not in log
    assert "restart odsod-daemon-pipeline.service" not in log
    (installed / "systemctl.log").unlink()
    documents.write_json(
        installed / "config/config.json",
        {"inference": {"enabled": True, "llama": {"extra_args": ["--verbose"]}}},
    )
    apply(record())
    log = calls(installed)
    assert "restart odsod-daemon-llama.service" in log
    assert "restart odsod-daemon-whisper.service" not in log


@pytest.mark.parametrize("legacy", ["llama-server.service", "whisper-server.service"])
def test_refuses_while_the_machine_servers_run(installed, legacy):
    set_up_servers(installed)
    documents.write_json(installed / "systemctl.json", {legacy: "active"})
    with pytest.raises(ApplyError) as error:
        apply(record())
    message = str(error.value)
    assert legacy in message
    assert "systemctl --user disable --now llama-server whisper-server" in message
    assert "systemctl --user enable --now llama-server whisper-server" in message
    assert not (installed / "state/install/current").exists()
    assert not unit_file("odsod-daemon-pipeline.service").exists()


def test_machine_servers_do_not_block_a_client_host(installed):
    documents.write_json(
        installed / "systemctl.json", {"llama-server.service": "active"}
    )
    apply(record())
    assert (installed / "state/install/current").exists()


def test_invalid_inference_section_fails_clearly(installed):
    documents.write_json(
        installed / "config/config.json", {"inference": {"enabled": "maybe"}}
    )
    with pytest.raises(ApplyError, match="inference"):
        apply(record())
