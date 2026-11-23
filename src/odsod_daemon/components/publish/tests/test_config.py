"""Table tests for the publishing config section."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from odsod_daemon.components.publish.config import PublishingConfig
from odsod_daemon.lib import config


def write(root: Path, section: dict) -> None:
    (root / "config/config.json").write_text(json.dumps({"publishing": section}))


def test_defaults() -> None:
    settings = PublishingConfig()
    assert settings.targets == []
    assert settings.scan_s == 5
    assert settings.retry_s == 30


def test_home_is_expanded(temp_root, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(temp_root / "home"))
    write(
        temp_root,
        {"targets": [{"name": "vault", "dir": "~/inbox", "types": ["transcripts"]}]},
    )
    settings = config.section("publishing", PublishingConfig)
    assert settings.targets[0].dir == temp_root / "home/inbox"


@pytest.mark.parametrize(
    "target",
    [
        {"name": "Vault", "dir": "/tmp/x", "types": ["transcripts"]},
        {"name": "in box", "dir": "/tmp/x", "types": ["transcripts"]},
        {"name": "vault", "dir": "relative", "types": ["transcripts"]},
        {"name": "vault", "dir": "/tmp/x", "types": []},
        {"name": "vault", "dir": "/tmp/x", "types": ["audio"]},
    ],
)
def test_bad_target_is_rejected(temp_root, target) -> None:
    write(temp_root, {"targets": [target]})
    with pytest.raises(ValidationError):
        config.section("publishing", PublishingConfig)


def test_duplicate_names_are_rejected(temp_root) -> None:
    write(
        temp_root,
        {
            "targets": [
                {"name": "vault", "dir": "/tmp/a", "types": ["transcripts"]},
                {"name": "vault", "dir": "/tmp/b", "types": ["interactions"]},
            ]
        },
    )
    with pytest.raises(ValidationError):
        config.section("publishing", PublishingConfig)
