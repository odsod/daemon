"""Retention: pure hour rules and the ``odsodctl retention`` command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.retention import retention

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _touch(root: Path, channel: str, hour: str, size: int = 16) -> Path:
    directory = root / "state" / "audio" / channel
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{hour}.pcm"
    path.write_bytes(b"\0" * size)
    return path


def _config(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "config.json").write_text(
        json.dumps(
            {
                "common": {
                    "inference": {
                        "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
                        "llama_url": "http://127.0.0.1:8188/v1/chat/completions",
                    }
                }
            }
        )
    )


def test_hour_start_parses_and_rejects() -> None:
    assert retention.hour_start(Path("20261122T14Z.pcm")) == datetime(
        2026, 11, 22, 14, 0, tzinfo=UTC
    )
    assert retention.hour_start(Path("notes.pcm")) is None
    assert retention.hour_start(Path("20261322T14Z.pcm")) is None


def test_files_to_delete_uses_the_first_second() -> None:
    files = [
        Path("20261109T11Z.pcm"),
        Path("20261109T12Z.pcm"),
        Path("20261109T13Z.pcm"),
        Path("20261123T11Z.pcm"),
        Path("notes.pcm"),
    ]
    assert retention.files_to_delete(files, NOW, 14) == [
        Path("20261109T11Z.pcm"),
        Path("20261109T12Z.pcm"),
    ]


def test_audio_files_lists_channels_and_skips_symlinks(tmp_path: Path) -> None:
    _touch(tmp_path, "mic", "20261122T14Z")
    _touch(tmp_path, "sys", "20261122T15Z")
    (tmp_path / "state" / "audio" / "mic" / "notes.txt").write_text("keep")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.pcm").write_bytes(b"\0")
    (tmp_path / "state" / "audio" / "extra").symlink_to(outside)
    (tmp_path / "state" / "audio" / "mic" / "link.pcm").symlink_to(outside / "x.pcm")
    found = retention.audio_files(tmp_path / "state")
    assert [path.name for path in found] == [
        "20261122T14Z.pcm",
        "20261122T15Z.pcm",
    ]
    assert (tmp_path / "state" / "bench").exists() is False


def test_command_deletes_old_audio_and_keeps_young(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _config(tmp_path)
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    old = _touch(tmp_path, "mic", "20200101T00Z")
    young = _touch(tmp_path, "sys", "29990101T00Z")
    result = CliRunner().invoke(app, ["retention"])
    assert result.exit_code == 0, result.output
    assert not old.exists()
    assert young.exists()


def test_command_exits_non_zero_when_a_delete_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _config(tmp_path)
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    old = _touch(tmp_path, "mic", "20200101T00Z")
    directory = old.parent
    directory.chmod(0o500)
    try:
        result = CliRunner().invoke(app, ["retention"])
    finally:
        directory.chmod(0o700)
    assert result.exit_code == 1
    assert "Permission denied" in result.output


def test_command_fails_without_a_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["retention"])
    assert result.exit_code == 1
    assert "file not found" in result.output
