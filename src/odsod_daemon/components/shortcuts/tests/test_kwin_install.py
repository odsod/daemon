import json
import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from odsod_daemon.components.shortcuts import kwin_install
from odsod_daemon.components.shortcuts.contract import LIST_PATH
from odsod_daemon.lib import clock


class FakeKDE:
    """Fake kpackagetool6, kwriteconfig6 and KWin reconfigure.

    kpackagetool6 copies the package into ``installed``, as the real tool does.
    """

    def __init__(self, installed: Path, failures: int = 0) -> None:
        self.installed = installed
        self.failures = failures
        self.calls: list[str] = []

    async def run(self, command: Sequence[str]) -> None:
        if command[0] == "kpackagetool6":
            self.calls.append(" ".join(command[:3]))
        else:
            self.calls.append(f"{command[0]} {command[-1]}")
        if self.failures:
            self.failures -= 1
            raise RuntimeError("kpackagetool6 exit 1: KWin not running")
        if command[0] == "kpackagetool6":
            shutil.copytree(command[3], self.installed, dirs_exist_ok=True)

    async def reload(self) -> None:
        self.calls.append("reconfigure")


def embedded_list(script: str) -> list[dict]:
    start = script.index("const shortcuts = ") + len("const shortcuts = ")
    end = script.index("\n];\n", start) + 2
    return json.loads(script[start:end])


def test_render_replaces_the_placeholder_with_the_list(tmp_path: Path):
    kwin_install.render(tmp_path / "pkg")

    script = (tmp_path / "pkg" / kwin_install.SCRIPT).read_text()
    assert "/*@shortcuts@*/" not in script
    expected = json.loads(LIST_PATH.read_text())["shortcuts"]
    assert embedded_list(script) == expected
    metadata = json.loads((tmp_path / "pkg/metadata.json").read_text())
    assert metadata["KPlugin"]["Id"] == "odsod-daemon"


def test_installed_dir_follows_xdg_data_home():
    env = {"HOME": "/h", "XDG_DATA_HOME": "/d"}
    assert kwin_install.installed_dir(env) == Path("/d/kwin/scripts/odsod-daemon")
    assert kwin_install.installed_dir({"HOME": "/h"}) == Path(
        "/h/.local/share/kwin/scripts/odsod-daemon"
    )


async def test_missing_package_installs_and_toggles_the_plugin(tmp_path: Path):
    installed = tmp_path / "scripts/odsod-daemon"
    kde = FakeKDE(installed)

    assert await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed
    )

    assert kde.calls == [
        "kpackagetool6 --type=KWin/Script --install",
        "kwriteconfig6 false",
        "reconfigure",
        "kwriteconfig6 true",
        "reconfigure",
    ]


async def test_same_package_on_disk_gives_no_tool_call_and_no_reload(tmp_path: Path):
    installed = tmp_path / "scripts/odsod-daemon"
    kwin_install.render(installed)
    kde = FakeKDE(installed)

    assert await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed
    )

    assert kde.calls == []


async def test_changed_list_upgrades(tmp_path: Path):
    installed = tmp_path / "scripts/odsod-daemon"
    kwin_install.render(installed)
    changed = tmp_path / "shortcuts.json"
    data = json.loads(LIST_PATH.read_text())
    data["shortcuts"].pop()
    changed.write_text(json.dumps(data))
    kde = FakeKDE(installed)

    await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed, list_path=changed
    )

    assert kde.calls[0] == "kpackagetool6 --type=KWin/Script --upgrade"
    assert kde.calls.count("reconfigure") == 2
    assert (
        embedded_list((installed / kwin_install.SCRIPT).read_text())
        == data["shortcuts"]
    )


async def test_two_failures_then_success_retries_with_backoff(tmp_path: Path):
    installed = tmp_path / "scripts/odsod-daemon"
    kde = FakeKDE(installed, failures=2)
    start = clock.monotonic()

    assert await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed
    )

    assert clock.monotonic() - start == pytest.approx(3.0)
    assert kde.calls.count("reconfigure") == 2


async def test_three_failures_give_one_log_line(tmp_path: Path, caplog):
    installed = tmp_path / "scripts/odsod-daemon"
    kde = FakeKDE(installed, failures=99)

    ok = await kwin_install.ensure(run=kde.run, reload=kde.reload, installed=installed)

    assert not ok
    assert kde.calls.count("kpackagetool6 --type=KWin/Script --install") == 3
    assert "reconfigure" not in kde.calls
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == [
        "kwin script: install failed after 3 tries: "
        "kpackagetool6 exit 1: KWin not running"
    ]
