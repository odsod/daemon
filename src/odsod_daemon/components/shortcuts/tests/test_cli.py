import json

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.shortcuts import contract


def test_json_holds_every_chord_and_action():
    result = CliRunner().invoke(app, ["shortcuts", "--json"])

    assert result.exit_code == 0
    printed = json.loads(result.stdout)["shortcuts"]
    expected = contract.load().shortcuts
    assert [(s["key"], s["action_id"]) for s in printed] == [
        (s.key, s.action_id) for s in expected
    ]


def test_text_has_one_line_per_chord():
    result = CliRunner().invoke(app, ["shortcuts"])

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert len(lines) == len(contract.load().shortcuts)
    meet = next(line for line in lines if "[odsod] meet" in line)
    assert meet.startswith("Meta+M ")
    assert " app " in meet
    assert "--app=https://meet.google.com" in meet
    close = next(line for line in lines if "Window Close" in line)
    assert close.split()[:2] == ["Meta+Backspace", "builtin"]
