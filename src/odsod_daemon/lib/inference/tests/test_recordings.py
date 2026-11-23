"""Checks that the recorded pairs are complete and replay through the fake."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from odsod_daemon.lib import inference

TESTDATA = Path(__file__).parents[1] / "testdata"
RECORDINGS = sorted(TESTDATA.glob("*.json"))
PATHS = {inference.WHISPER_PATH, inference.LLAMA_PATH}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def test_has_at_least_nine_recordings() -> None:
    assert len(RECORDINGS) >= 9


def test_every_recording_has_request_and_response() -> None:
    for path in RECORDINGS:
        record = _load(path)
        request = record["request"]
        response = record["response"]
        assert request["method"] == "POST", path
        assert request["path"] in PATHS, path
        assert "headers" in request, path
        assert "body" in request, path
        assert "status" in response, path
        assert "headers" in response, path
        assert "elapsed_ms" in response, path
        assert "json" in response or "body" in response, path


def test_fake_replays_every_recording() -> None:
    server = inference.ReplayServer(inference.load_pairs(TESTDATA))
    try:
        with httpx.Client(timeout=10.0) as client:
            for path in RECORDINGS:
                record = _load(path)
                request = record["request"]
                expected = record["response"]
                if request["path"] == inference.WHISPER_PATH:
                    body = request["body"]
                    fields = body.get("fields", {})
                    file = body.get("file")
                    if file is None:
                        response = client.post(
                            server.url + request["path"], data=fields
                        )
                    else:
                        response = client.post(
                            server.url + request["path"],
                            data=fields,
                            files={
                                "file": (
                                    file["filename"],
                                    b"RIFF....",
                                    file["content_type"],
                                )
                            },
                        )
                else:
                    response = client.post(
                        server.url + request["path"], json=request["body"]
                    )
                assert response.status_code == expected["status"], path
                if "json" in expected:
                    assert response.json() == expected["json"], path
                else:
                    assert response.text == expected.get("body", ""), path
    finally:
        server.close()
