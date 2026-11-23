import json

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    StatusReport,
)


@pytest.mark.parametrize(
    "state,exit_code", [("running", 0), ("warning", 1), ("error", 2), ("unknown", 3)]
)
def test_status_exit_codes(fake_control, monkeypatch, state, exit_code):
    async def report():
        return StatusReport(
            state=state,
            exit_code=exit_code,
            backlog=Backlog(count=2, seconds=12),
            mode="idle",
            dictation=DictationState(available=False, reason="session-down"),
            ts="now",
        )

    monkeypatch.setattr("odsod_daemon.components.status.cli.report", report)
    result = CliRunner().invoke(app, ["status", "--json"])
    assert result.exit_code == exit_code
    data = json.loads(result.stdout)
    assert data["state"] == state
    text = CliRunner().invoke(app, ["status"]).stdout
    assert state in text
    assert "12 seconds" in text
    assert "session-down" in text
    assert data["ts"] in text


def test_status_unknown_on_unavailable_manager(fake_control, monkeypatch):
    async def broken():
        raise RuntimeError("manager unavailable")

    monkeypatch.setattr("odsod_daemon.components.status.cli.report", broken)
    result = CliRunner().invoke(app, ["status", "--json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["state"] == "unknown"
    assert "manager unavailable" in result.stdout
