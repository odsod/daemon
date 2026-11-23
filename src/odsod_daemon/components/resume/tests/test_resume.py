import json

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.pause import flag
from odsod_daemon.lib import streams


def test_resume_records_once_and_starts(fake_control):
    flag.write(fake_control / "run", "2026-11-23T12:00:00Z")
    runner = CliRunner()
    result = runner.invoke(app, ["resume", "--by", "login", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["changed"]
    assert flag.read(fake_control / "run") is None
    records = list((fake_control / "state/events/user").glob("*.jsonl"))
    assert streams.read_day(records[0])[0]["by"] == "login"
    result = runner.invoke(app, ["resume", "--json"])
    assert not json.loads(result.stdout)["changed"]
    assert len(streams.read_day(records[0])) == 1
    assert (
        "start odsod-daemon-capture.service"
        in (fake_control / "systemctl.log").read_text()
    )


def test_logged_out_resume_and_start_failure(fake_control, monkeypatch):
    (fake_control / "systemctl.json").write_text(
        json.dumps({"graphical-session.target": "inactive"})
    )
    flag.write(fake_control / "run", "2026-11-23T12:00:00Z")
    result = CliRunner().invoke(app, ["resume", "--by", "timer"])
    assert result.exit_code == 0
    assert not (fake_control / "run/paused").exists()
    assert (
        "start odsod-daemon-capture.service"
        not in (fake_control / "systemctl.log").read_text()
    )
    (fake_control / "systemctl.json").unlink()
    monkeypatch.setenv("FAKE_SYSTEMCTL_FAIL", "start odsod-daemon-capture.service")
    result = CliRunner().invoke(app, ["resume"])
    assert result.exit_code == 1
