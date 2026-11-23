import logging
from collections.abc import Sequence
from typing import IO

import pytest

from odsod_daemon.components.shortcuts import contract, launcher
from odsod_daemon.components.shortcuts.contract import Shortcut
from odsod_daemon.lib import clock


class FakeProcess:
    def __init__(self, code: int, after_s: float) -> None:
        self.code = code
        self.after_s = after_s

    async def wait(self) -> int:
        await clock.sleep(self.after_s)
        return self.code


class FakeSystemdRun:
    """Records each argv and writes stderr like a failed start would."""

    def __init__(self, code: int = 0, after_s: float = 0, stderr: bytes = b""):
        self.code = code
        self.after_s = after_s
        self.stderr = stderr
        self.calls: list[list[str]] = []

    async def __call__(self, command: Sequence[str], stderr: IO[bytes]) -> FakeProcess:
        self.calls.append(list(command))
        stderr.write(self.stderr)
        return FakeProcess(self.code, self.after_s)


def meet() -> Shortcut:
    return next(s for s in contract.load().shortcuts if s.name == "[odsod] meet")


def failures(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_unit_name():
    assert launcher.unit_name("[odsod] meet", "ab12") == "app-odsod-meet-ab12.scope"
    assert launcher.unit_name("[odsod] a b/c", "1") == "app-odsod-a-b-c-1.scope"


async def test_run_starts_systemd_run_scope_with_the_listed_argv(caplog):
    fake = FakeSystemdRun()
    await launcher.launch(meet(), start=fake)

    [call] = fake.calls
    assert call[:3] == ["systemd-run", "--user", "--scope"]
    assert call[3].startswith("--unit=app-odsod-meet-")
    assert call[3].endswith(".scope")
    assert call[4:6] == ["--collect", "--"]
    assert call[6:] == meet().command
    assert failures(caplog) == []


async def test_each_run_gets_its_own_unit():
    fake = FakeSystemdRun()
    await launcher.launch(meet(), start=fake)
    await launcher.launch(meet(), start=fake)
    assert fake.calls[0][3] != fake.calls[1][3]


async def test_a_command_that_fails_at_once_gives_one_log_line(caplog):
    fake = FakeSystemdRun(code=1, after_s=0.1, stderr=b"Failed to find executable\nx\n")
    await launcher.launch(meet(), start=fake)

    assert failures(caplog) == [
        "run [odsod] meet: start failed: exit 1: Failed to find executable"
    ]


async def test_an_app_that_runs_past_the_window_is_not_watched(caplog):
    fake = FakeSystemdRun(code=1, after_s=3600)
    start = clock.monotonic()
    await launcher.launch(meet(), start=fake)

    assert clock.monotonic() - start == pytest.approx(launcher.START_WINDOW_S)
    assert failures(caplog) == []


async def test_a_missing_systemd_run_gives_one_log_line(caplog):
    async def missing(command: Sequence[str], stderr: IO[bytes]) -> FakeProcess:
        raise FileNotFoundError(2, "No such file or directory", command[0])

    await launcher.launch(meet(), start=missing)

    [line] = failures(caplog)
    assert line.startswith("run [odsod] meet: start failed:")
    assert "systemd-run" in line


@pytest.mark.looptime(False)
async def test_real_spawn_runs_a_fake_systemd_run_from_path(
    tmp_path, monkeypatch, caplog
):
    log = tmp_path / "argv"
    fake = tmp_path / "systemd-run"
    fake.write_text(f'#!/bin/sh\necho "$@" > {log}\necho "Unit exists" >&2\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    await launcher.launch(meet())

    assert log.read_text().startswith("--user --scope --unit=app-odsod-meet-")
    assert failures(caplog) == ["run [odsod] meet: start failed: exit 1: Unit exists"]


def test_environment_puts_the_odsodctl_directory_first_once():
    env = launcher.environment({"PATH": "/usr/bin:/bin", "HOME": "/h"}, "/venv/bin")
    assert env == {"PATH": "/venv/bin:/usr/bin:/bin", "HOME": "/h"}
    again = launcher.environment({"PATH": "/usr/bin:/venv/bin"}, "/venv/bin")
    assert again["PATH"] == "/usr/bin:/venv/bin"
    assert launcher.environment({}, "/venv/bin")["PATH"] == "/venv/bin"


@pytest.mark.looptime(False)
async def test_launched_command_finds_odsodctl_on_path(tmp_path, monkeypatch, caplog):
    import sys
    from pathlib import Path

    seen = tmp_path / "path"
    fake = tmp_path / "systemd-run"
    fake.write_text(f'#!/bin/sh\necho "$PATH" > {seen}\nexit 0\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    await launcher.launch(meet())

    entries = seen.read_text().strip().split(":")
    assert str(Path(sys.executable).parent) in entries
