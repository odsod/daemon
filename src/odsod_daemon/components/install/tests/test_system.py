from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest

from odsod_daemon.components.install import system as install_system

FAKE_BIN = Path(__file__).parent / "bin"
ODSODCTL = Path("/usr/local/bin/odsodctl")


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "log"
    log.mkdir()
    monkeypatch.setenv("PATH", f"{FAKE_BIN}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(log))
    entry = pwd.getpwuid(os.getuid())
    monkeypatch.setenv("SUDO_UID", str(entry.pw_uid))
    monkeypatch.setenv("SUDO_GID", str(entry.pw_gid))
    monkeypatch.setenv("SUDO_USER", entry.pw_name)
    monkeypatch.delenv("FAKE_GCC_FAIL", raising=False)
    monkeypatch.delenv("FAKE_GCC_CONTENT", raising=False)
    return log


def calls(log: Path) -> list[str]:
    path = log / "systemctl.log"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def clear(log: Path) -> None:
    path = log / "systemctl.log"
    path.unlink(missing_ok=True)


def root(tmp_path: Path) -> Path:
    return tmp_path / "root"


def install(prefix: Path) -> install_system.SystemInstall:
    return install_system.install_system(prefix=prefix, odsodctl=ODSODCTL)


def test_first_install_writes_the_binary_and_units(
    tmp_path: Path, fake_tools: Path
) -> None:
    prefix = root(tmp_path)
    result = install(prefix)

    assert result.binary_changed is True
    assert result.unit_changed is True
    assert result.restarted is True

    binary = prefix / install_system.BINARY_PATH
    assert binary.read_text(encoding="utf-8") == "fake keys binary one\n"
    assert binary.stat().st_mode & 0o777 == 0o755

    entry = pwd.getpwuid(os.getuid())
    unit = (prefix / install_system.UNIT_PATH).read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/bin/odsod-daemon-keys" in unit
    assert "Restart=always" in unit
    assert "Nice=-20" in unit
    assert "RuntimeDirectory=odsod-daemon-keys" in unit
    assert f"chown {entry.pw_uid}:{entry.pw_gid} /run/odsod-daemon-keys" in unit

    dropin = (prefix / install_system.DROPIN_PATH).read_text(encoding="utf-8")
    assert "OnFailure=odsod-daemon-notify-system@%n.service" in dropin

    notify = (prefix / install_system.NOTIFY_PATH).read_text(encoding="utf-8")
    assert f"User={entry.pw_name}" in notify
    assert f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{entry.pw_uid}/bus" in notify
    assert f"ExecStart={ODSODCTL} notify-failed %i" in notify

    assert calls(fake_tools) == [
        "daemon-reload",
        "enable odsod-daemon-keys.service",
        "restart odsod-daemon-keys.service",
    ]


def test_second_install_with_no_change_restarts_nothing(
    tmp_path: Path, fake_tools: Path
) -> None:
    prefix = root(tmp_path)
    install(prefix)
    clear(fake_tools)

    result = install(prefix)
    assert result.binary_changed is False
    assert result.unit_changed is False
    assert result.restarted is False
    assert calls(fake_tools) == ["enable odsod-daemon-keys.service"]


def test_a_changed_binary_restarts_keys(
    tmp_path: Path, fake_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = root(tmp_path)
    install(prefix)
    clear(fake_tools)
    monkeypatch.setenv("FAKE_GCC_CONTENT", "two")

    result = install(prefix)
    assert result.binary_changed is True
    assert result.restarted is True
    assert "restart odsod-daemon-keys.service" in calls(fake_tools)
    assert (prefix / install_system.BINARY_PATH).read_text(
        encoding="utf-8"
    ) == "fake keys binary two\n"


def test_a_changed_unit_restarts_keys(tmp_path: Path, fake_tools: Path) -> None:
    prefix = root(tmp_path)
    install(prefix)
    clear(fake_tools)
    (prefix / install_system.UNIT_PATH).unlink()

    result = install(prefix)
    assert result.binary_changed is False
    assert result.unit_changed is True
    assert result.restarted is True
    assert calls(fake_tools) == [
        "daemon-reload",
        "enable odsod-daemon-keys.service",
        "restart odsod-daemon-keys.service",
    ]


def test_no_sudo_uid_refuses_and_writes_nothing(
    tmp_path: Path, fake_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUDO_UID")
    prefix = root(tmp_path)
    with pytest.raises(install_system.SystemError, match="SUDO_UID"):
        install(prefix)
    assert not prefix.exists()


def test_a_failed_build_keeps_the_old_binary(
    tmp_path: Path, fake_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = root(tmp_path)
    install(prefix)
    clear(fake_tools)
    monkeypatch.setenv("FAKE_GCC_FAIL", "1")

    with pytest.raises(install_system.SystemError, match="gcc failed"):
        install(prefix)
    assert (prefix / install_system.BINARY_PATH).read_text(
        encoding="utf-8"
    ) == "fake keys binary one\n"
    assert calls(fake_tools) == []


def test_units_are_written_with_the_owner_mode(
    tmp_path: Path, fake_tools: Path
) -> None:
    prefix = root(tmp_path)
    install(prefix)
    for path in (
        install_system.UNIT_PATH,
        install_system.DROPIN_PATH,
        install_system.NOTIFY_PATH,
    ):
        assert (prefix / path).stat().st_mode & 0o777 == 0o644
