import json
import subprocess
import sys

from typer.testing import CliRunner

from odsod_daemon.cli import app


def test_notification_and_failure(fake_control, monkeypatch):
    for unit, prefix in [("pipeline", "systemctl --user"), ("keys", "sudo systemctl")]:
        result = CliRunner().invoke(
            app, ["notify-failed", f"odsod-daemon-{unit}.service"]
        )
        assert result.exit_code == 0
        call = json.loads((fake_control / "notify.log").read_text().splitlines()[-1])
        assert "--urgency=critical" in call
        assert prefix in call[-1]
    assert len((fake_control / "notify.log").read_text().splitlines()) == 2
    monkeypatch.setenv("FAKE_NOTIFY_FAIL", "1")
    result = CliRunner().invoke(app, ["notify-failed", "odsod-daemon-pipeline.service"])
    assert "notify-send failed" in result.stderr
    assert len((fake_control / "notify.log").read_text().splitlines()) == 3


def test_notification_does_not_load_qt():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import odsod_daemon.components.notify_failed.cli; "
                'assert not any(m.startswith("PySide6") for m in sys.modules)'
            ),
        ],
        timeout=10,
    )
    assert result.returncode == 0
