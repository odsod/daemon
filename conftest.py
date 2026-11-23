"""Shared fake user-manager and desktop tools for command checks."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def fake_control(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(root))
    monkeypatch.setenv(
        "PATH", f"{Path(__file__).parent / 'tests/bin'}:{os.environ['PATH']}"
    )
    return root
