import json
import logging
import shutil
from collections.abc import Sequence
from functools import partial
from pathlib import Path

import pytest

from odsod_daemon.components.shortcuts import kwin_install
from odsod_daemon.components.shortcuts.contract import LIST_PATH
from odsod_daemon.lib import clock


class FakeKDE:
    """Fake kpackagetool6, kwriteconfig6 and KWin reconfigure.

    kpackagetool6 copies the package into ``installed`` and kwriteconfig6
    writes ``kwinrc``, as the real tools do.
    """

    def __init__(
        self, installed: Path, failures: int = 0, reload_failures: int = 0
    ) -> None:
        self.installed = installed
        self.kwinrc = installed.parent / "kwinrc"
        self.failures = failures
        self.reload_failures = reload_failures
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
        if command[0] == "kwriteconfig6":
            self.enable(command[-1])

    def enable(self, value: str) -> None:
        self.kwinrc.parent.mkdir(parents=True, exist_ok=True)
        self.kwinrc.write_text(
            f"[Desktops]\nNumber=1\n\n[Plugins]\nblurEnabled=true\n"
            f"odsod-daemonEnabled={value}\n"
        )

    async def reload(self) -> None:
        self.calls.append("reconfigure")
        if self.reload_failures:
            self.reload_failures -= 1
            raise RuntimeError("org.freedesktop.DBus.Error.ServiceUnknown")


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
        run=kde.run, reload=kde.reload, installed=installed, kwinrc=kde.kwinrc
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
    kde.enable("true")

    assert await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed, kwinrc=kde.kwinrc
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
        run=kde.run,
        reload=kde.reload,
        installed=installed,
        kwinrc=kde.kwinrc,
        list_path=changed,
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
        run=kde.run, reload=kde.reload, installed=installed, kwinrc=kde.kwinrc
    )

    assert clock.monotonic() - start == pytest.approx(3.0)
    assert kde.calls.count("reconfigure") == 2


async def test_three_failures_give_one_log_line(tmp_path: Path, caplog):
    installed = tmp_path / "scripts/odsod-daemon"
    kde = FakeKDE(installed, failures=99)

    ok = await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed, kwinrc=kde.kwinrc
    )

    assert not ok
    assert kde.calls.count("kpackagetool6 --type=KWin/Script --install") == 3
    assert "reconfigure" not in kde.calls
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == [
        "kwin script: install failed after 3 tries: "
        "kpackagetool6 exit 1: KWin not running"
    ]


@pytest.mark.parametrize("state", ["missing", "false"])
async def test_same_package_with_the_plugin_disabled_enables_it(
    tmp_path: Path, state: str
):
    installed = tmp_path / "scripts/odsod-daemon"
    kwin_install.render(installed)
    kde = FakeKDE(installed)
    if state == "false":
        kde.enable("false")

    assert await kwin_install.ensure(
        run=kde.run, reload=kde.reload, installed=installed, kwinrc=kde.kwinrc
    )

    assert kde.calls[-2:] == ["kwriteconfig6 true", "reconfigure"]
    assert kwin_install.enabled(kde.kwinrc)


async def test_failed_reload_is_retried_at_the_next_start(tmp_path: Path):
    installed = tmp_path / "scripts/odsod-daemon"
    kde = FakeKDE(installed, reload_failures=3)
    ensure = partial(
        kwin_install.ensure,
        run=kde.run,
        reload=kde.reload,
        installed=installed,
        kwinrc=kde.kwinrc,
    )

    assert not await ensure()
    kde.calls.clear()
    assert await ensure()

    assert kde.calls[-1] == "reconfigure"
    assert kwin_install.enabled(kde.kwinrc)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[Plugins]\nodsod-daemonEnabled=true\n", True),
        ("[Plugins]\nodsod-daemonEnabled = true\n", True),
        ("[Plugins]\nodsod-daemonEnabled=false\n", False),
        ("[Other]\nodsod-daemonEnabled=true\n", False),
        ("[Plugins]\nodsodEnabled=true\n", False),
    ],
)
def test_enabled_reads_the_plugins_group(tmp_path: Path, text: str, expected: bool):
    kwinrc = tmp_path / "kwinrc"
    kwinrc.write_text(text)
    assert kwin_install.enabled(kwinrc) is expected
