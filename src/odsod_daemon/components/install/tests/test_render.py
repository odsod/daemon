from pathlib import Path

from odsod_daemon.components.install import render


def test_shipped_templates(tmp_path: Path):
    rendered = render.render(Path("/opt/my app/odsodctl"), {"HOME": str(tmp_path)})
    files = {p.name: text for p, text in rendered.items()}
    assert set(files) == {
        *render.SUPPORT,
        "odsod-daemon-capture.service",
        "odsod-daemon-pipeline.service",
        "odsod-daemon-tray.service",
    }
    capture = files["odsod-daemon-capture.service"]
    assert "ExecCondition=/bin/sh -c '! test -e %t/odsod-daemon/paused'" in capture
    assert 'ExecStart="/opt/my app/odsodctl" run capture' in capture
    assert "WatchdogSec=30" in capture
    assert "WantedBy=graphical-session.target" in capture
    assert "odsod-daemon-pipeline.service" in files["odsod-daemon.target"]
    for name, text in files.items():
        assert "{{" not in text
        assert "EnvironmentFile=" not in text
        assert "LoadCredential=" not in text
        if name not in {"odsod-daemon-notify@.service", render.DBUS}:
            assert "OnFailure=odsod-daemon-notify@%n.service" in text


def test_future_session_and_tray_templates(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(render, "SERVICES", ("capture", "pipeline", "session", "tray"))
    files = {
        p.name: text
        for p, text in render.render(Path("/bin/true"), {"HOME": str(tmp_path)}).items()
    }
    assert render.DBUS in files
    assert (
        'ExecStopPost="/bin/true" unmute-stale' in files["odsod-daemon-session.service"]
    )
    assert "PartOf=graphical-session.target" in files["odsod-daemon-tray.service"]
    session = files["odsod-daemon-session.service"]
    assert 'ExecStart="/bin/true" run session' in session
    assert 'ExecStopPost="/bin/true" unmute-stale' in session
    assert (
        "After=pipewire.service wireplumber.service graphical-session.target" in session
    )
    assert "WantedBy=graphical-session.target" in session
    assert "PartOf=graphical-session.target" in session
    assert "WatchdogSec=" not in session
