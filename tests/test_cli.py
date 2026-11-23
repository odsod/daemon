"""The root CLI: ``run`` refuses a bad name without a traceback."""

from __future__ import annotations

from typer.testing import CliRunner

from odsod_daemon.cli import app


def test_run_with_a_bad_name_exits_cleanly() -> None:
    result = CliRunner().invoke(app, ["run", "not a component"])
    assert result.exit_code == 2
    assert "bad component name" in result.output
    assert "Traceback" not in result.output
