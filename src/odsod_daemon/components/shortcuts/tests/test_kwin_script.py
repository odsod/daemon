"""Run the rendered KWin script under node against a fake KWin API."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from odsod_daemon.components.shortcuts import contract, kwin_install

NODE = shutil.which("node")
HARNESS = Path(__file__).parent / "testdata" / "fake_kwin.js"
DBUS = [
    "io.github.odsod.daemon.session",
    "/io/github/odsod/daemon/shortcuts",
    "io.github.odsod.daemon.Shortcuts",
]

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

SLACK = {"resourceClass": "slack"}
OTHER = {"resourceClass": "org.mozilla.firefox"}


def run_script(
    tmp_path: Path, windows: list[dict], active: int | None, press: list[str]
) -> dict[str, Any]:
    assert NODE is not None
    kwin_install.render(tmp_path / "pkg")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"windows": windows, "active": active, "press": press})
    )
    output = subprocess.run(
        [
            NODE,
            str(HARNESS),
            str(tmp_path / "pkg" / kwin_install.SCRIPT),
            str(scenario),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout
    return json.loads(output)


def calls(result: dict[str, Any], method: str) -> list[list[str]]:
    return [e[5:] for e in result["events"] if e[0] == "dbus" and e[4] == method]


def test_load_registers_own_chords_and_calls_configure(tmp_path: Path):
    result = run_script(tmp_path, [], None, [])

    registered = [e[1:] for e in result["events"] if e[0] == "register"]
    shortcuts = contract.load().shortcuts
    assert registered == [[s.name, s.key] for s in shortcuts if s.kind != "builtin"]
    assert calls(result, "Configure") == [[]]
    assert all(e[1:4] == DBUS for e in result["events"] if e[0] == "dbus")


def test_app_chord_with_no_window_runs_the_app_by_name(tmp_path: Path):
    result = run_script(tmp_path, [OTHER], 0, ["[odsod] slack"])
    assert calls(result, "Run") == [["[odsod] slack"]]


def test_app_chord_activates_the_window_used_last(tmp_path: Path):
    result = run_script(tmp_path, [SLACK, SLACK, OTHER], 2, ["[odsod] slack"])
    assert result["active"] == 1
    assert calls(result, "Run") == []


def test_app_chord_on_the_active_window_minimizes_then_restores(tmp_path: Path):
    result = run_script(tmp_path, [OTHER, SLACK], 1, ["[odsod] slack", "[odsod] slack"])
    assert result["active"] == 1
    assert result["windows"][1]["minimized"] is False

    once = run_script(tmp_path, [OTHER, SLACK], 1, ["[odsod] slack"])
    assert once["windows"][1]["minimized"] is True


def test_command_chord_runs_by_name(tmp_path: Path):
    result = run_script(tmp_path, [], None, ["[odsod] run", "[odsod] debug"])
    assert calls(result, "Run") == [["[odsod] run"]]


def test_no_border_is_applied_to_open_windows(tmp_path: Path):
    result = run_script(tmp_path, [SLACK, OTHER], 0, [])
    assert [w["noBorder"] for w in result["windows"]] == [True, False]
