from pathlib import Path

from odsod_daemon.components.install import render


def test_shipped_templates(tmp_path: Path):
    rendered = render.render(Path("/opt/my app/odsodctl"), {"HOME": str(tmp_path)})
    files = {p.name: text for p, text in rendered.items()}
    assert set(files) == {
        *render.SUPPORT,
        "odsod-daemon-capture.service",
        "odsod-daemon-pipeline.service",
        "odsod-daemon-session.service",
        "odsod-daemon-tray.service",
        render.DBUS,
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


def test_server_units_carry_the_command_line(tmp_path: Path):
    from odsod_daemon.components.servers.contract import SERVERS, Inference

    settings = Inference.model_validate(
        {"enabled": True, "llama": {"port": 9000, "extra_args": ["--slots"]}}
    )
    state = tmp_path / "my state"
    servers = {s.unit: render.server_command(s, settings, state) for s in SERVERS}
    files = {
        p.name: text
        for p, text in render.render(
            Path("/bin/true"), {"HOME": str(tmp_path)}, servers=servers
        ).items()
    }
    llama = files["odsod-daemon-llama.service"]
    binary = state / "servers/llama.cpp-1.0.0-b12359-b1b770d/build/bin/llama-server"
    assert f'ExecStart="{binary}" "--model" "{state}/models/' in llama
    assert '"--port" "9000"' in llama
    assert llama.rstrip().endswith("WantedBy=odsod-daemon.target")
    assert '"--spec-ngram-simple-size-m" "32" "--slots"' in llama
    whisper = files["odsod-daemon-whisper.service"]
    assert '"--port" "8178"' in whisper
    for text in (llama, whisper):
        assert "Type=simple" in text
        assert "Restart=on-failure" in text
        assert "RestartSec=5" in text
        assert "OnFailure=odsod-daemon-notify@%n.service" in text
