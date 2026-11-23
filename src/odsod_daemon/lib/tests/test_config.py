from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from odsod_daemon.lib import config, paths


def write_config(root: Path, value: object) -> paths.Roots:
    roots = paths.Roots(state=root / "state", run=root / "run", config=root / "config")
    roots.ensure()
    roots.config_file.write_text(json.dumps(value), encoding="utf-8")
    return roots


VALID = {
    "common": {
        "host": "work-laptop",
        "retention_days": 14,
        "inference": {
            "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
            "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
        },
    }
}


def test_common_fields(tmp_path: Path) -> None:
    roots = write_config(tmp_path, VALID)
    common = config.load_common(roots)
    assert common.host == "work-laptop"
    assert common.retention_days == 14
    assert common.inference.whisper_url.endswith("/v1/audio/transcriptions")


def test_common_defaults(tmp_path: Path) -> None:
    roots = write_config(
        tmp_path,
        {"common": {"inference": VALID["common"]["inference"]}},
    )
    common = config.load_common(roots)
    assert common.host == socket.gethostname()
    assert common.retention_days == 14


def test_rejects_url_outside_localhost_and_tailnet(tmp_path: Path) -> None:
    roots = write_config(
        tmp_path,
        {
            "common": {
                "inference": {
                    "whisper_url": "https://example.com/v1/audio/transcriptions",
                    "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
                }
            }
        },
    )
    with pytest.raises(ValueError):
        config.load_common(roots)


def test_section_uses_model_defaults(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class Reading(BaseModel):
        chunk_chars: int = 12_000

    roots = write_config(tmp_path, VALID)
    assert config.section("interactions", Reading, roots=roots).chunk_chars == 12_000


def test_section_reads_values(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class Reading(BaseModel):
        chunk_chars: int = 1

    roots = write_config(tmp_path, VALID | {"interactions": {"chunk_chars": 9000}})
    assert config.section("interactions", Reading, roots=roots).chunk_chars == 9000


def test_check_reports_all_errors(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class Reading(BaseModel):
        chunk_chars: int

    roots = write_config(
        tmp_path,
        {
            "common": {
                "retention_days": 0,
                "inference": {
                    "whisper_url": "https://example.com/x",
                    "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
                },
            },
            "interactions": {},
        },
    )
    errors = config.check({"interactions": Reading}, roots=roots)
    assert any("retention_days" in error for error in errors)
    assert any("whisper_url" in error for error in errors)
    assert any("chunk_chars" in error for error in errors)


def test_check_valid_config_has_no_errors(tmp_path: Path) -> None:
    roots = write_config(tmp_path, VALID)
    assert config.check({}, roots=roots) == []


def test_missing_config_file(tmp_path: Path) -> None:
    roots = paths.Roots(
        state=tmp_path / "state", run=tmp_path / "run", config=tmp_path / "config"
    )
    with pytest.raises(config.ConfigError, match="file not found"):
        config.load_common(roots)
