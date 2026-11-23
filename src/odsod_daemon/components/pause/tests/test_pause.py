import json

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.pause import flag
from odsod_daemon.lib import streams


def test_pause_order_and_idempotence(fake_control, monkeypatch):
    def stop(*args):
        assert flag.read(fake_control / "run") is not None
        files = list((fake_control / "state/events/user").glob("*.jsonl"))
        assert streams.read_day(files[0])[0]["kind"] == "pause"
        assert args == ("stop", "odsod-daemon-capture.service")

    monkeypatch.setattr("odsod_daemon.components.pause.cli.systemd.control", stop)
    runner = CliRunner()
    result = runner.invoke(app, ["pause", "--by", "tray", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["changed"]
    again = runner.invoke(app, ["pause", "--json"])
    assert not json.loads(again.stdout)["changed"]
    assert len(list((fake_control / "state/events/user").glob("*.jsonl"))) == 1


def test_failed_stop_keeps_flag(fake_control, monkeypatch):
    monkeypatch.setenv("FAKE_SYSTEMCTL_FAIL", "stop odsod-daemon-capture.service")
    result = CliRunner().invoke(app, ["pause"])
    assert result.exit_code == 1
    assert flag.read(fake_control / "run")
