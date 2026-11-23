from __future__ import annotations

import os
from pathlib import Path

from odsod_daemon.lib import paths


def test_override_uses_one_root() -> None:
    roots = paths.roots({"ODSOD_DAEMON_ROOT": "/tmp/example"})
    assert roots == paths.Roots(
        state=Path("/tmp/example/state"),
        run=Path("/tmp/example/run"),
        config=Path("/tmp/example/config"),
    )


def test_xdg_variables() -> None:
    roots = paths.roots(
        {
            "HOME": "/home/owner",
            "XDG_STATE_HOME": "/state",
            "XDG_RUNTIME_DIR": "/runtime",
            "XDG_CONFIG_HOME": "/config",
        }
    )
    assert roots.state == Path("/state/odsod-daemon")
    assert roots.run == Path("/runtime/odsod-daemon")
    assert roots.config == Path("/config/odsod-daemon")


def test_defaults_under_home() -> None:
    roots = paths.roots({"HOME": "/home/owner"})
    assert roots.state == Path("/home/owner/.local/state/odsod-daemon")
    assert roots.config == Path("/home/owner/.config/odsod-daemon")
    assert roots.run == Path(f"/run/user/{os.getuid()}/odsod-daemon")


def test_ensure_creates_roots(tmp_path: Path) -> None:
    roots = paths.Roots(
        state=tmp_path / "state",
        run=tmp_path / "run",
        config=tmp_path / "config",
    )
    roots.ensure()
    for path in (roots.state, roots.run, roots.config):
        assert path.is_dir()
        assert path.stat().st_mode & 0o777 == 0o700


def test_config_file(tmp_path: Path) -> None:
    roots = paths.Roots(
        state=tmp_path / "state",
        run=tmp_path / "run",
        config=tmp_path / "config",
    )
    assert roots.config_file == tmp_path / "config" / "config.json"
