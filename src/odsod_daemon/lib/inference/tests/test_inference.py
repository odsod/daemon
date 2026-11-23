from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from odsod_daemon.lib import inference

WHISPER = "http://127.0.0.1:8178/v1/audio/transcriptions"
LLAMA = "http://127.0.0.1:8179/v1/chat/completions"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8178/v1/audio/transcriptions",
        "http://127.0.0.1:8178/v1/audio/transcriptions",
        "http://[::1]:8178/v1/audio/transcriptions",
        "http://100.100.1.2:8178/v1/audio/transcriptions",
        "http://[fd7a:115c:a1e0::1]:8178/v1/audio/transcriptions",
        "https://work-laptop.ts.net/v1/audio/transcriptions",
    ],
)
def test_check_url_accepts_local_and_tailnet(url: str) -> None:
    assert inference.check_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/v1/audio/transcriptions",
        "http://192.168.1.5/v1/audio/transcriptions",
        "http://8.8.8.8/v1/chat/completions",
        "ftp://localhost/x",
        "http:///x",
    ],
)
def test_check_url_rejects_others(url: str) -> None:
    with pytest.raises(inference.InvalidInferenceURL):
        inference.check_url(url)


def test_is_loopback() -> None:
    assert inference.is_loopback("http://localhost:1/x")
    assert inference.is_loopback("http://127.1.2.3:1/x")
    assert not inference.is_loopback("http://100.100.1.2:1/x")


def test_is_tailnet() -> None:
    assert inference.is_tailnet("http://100.64.0.1:8178/x")
    assert inference.is_tailnet("http://[fd7a:115c:a1e0::2]:8178/x")
    assert inference.is_tailnet("https://work-laptop.ts.net/x")
    assert not inference.is_tailnet("http://127.0.0.1:8178/x")
    assert not inference.is_tailnet("http://example.com/x")


@pytest.mark.looptime(False)
async def test_reachable_to_open_port() -> None:
    server = inference.ReplayServer([])
    try:
        assert await inference.reachable(server.url, timeout_s=1)
    finally:
        server.close()


@pytest.mark.looptime(False)
async def test_reachable_to_closed_port() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert not await inference.reachable(f"http://127.0.0.1:{port}/x", timeout_s=1)


@pytest.mark.looptime(False)
async def test_whisper_client_posts_multipart() -> None:
    pair = {
        "request": {"method": "POST", "path": inference.WHISPER_PATH},
        "response": {"status": 200, "json": {"text": "hej", "language": "sv"}},
    }
    server = inference.ReplayServer([pair])
    try:
        client = inference.WhisperClient(server.url + inference.WHISPER_PATH)
        result = await client.transcribe(
            b"RIFF....", fields={"model": "whisper-1", "language": "sv"}
        )
    finally:
        server.close()
    assert result.text == "hej"
    assert result.language == "sv"
    sent = server.requests[0]
    assert sent["method"] == "POST"
    assert b"whisper-1" in sent["body"]


@pytest.mark.looptime(False)
async def test_llama_client_returns_message() -> None:
    pair = {
        "request": {"method": "POST", "path": inference.LLAMA_PATH},
        "response": {
            "status": 200,
            "json": {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        },
    }
    server = inference.ReplayServer([pair])
    try:
        client = inference.LlamaClient(server.url + inference.LLAMA_PATH)
        text = await client.complete([inference.ChatMessage(role="user", content="hi")])
    finally:
        server.close()
    assert text == "ok"
    assert b'"messages"' in server.requests[0]["body"]


@pytest.mark.looptime(False)
async def test_fake_returns_500_without_pair() -> None:
    server = inference.ReplayServer([])
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(server.url + inference.WHISPER_PATH)
    finally:
        server.close()
    assert response.status_code == 500


def test_load_pairs_one_file_per_pair(tmp_path: Path) -> None:
    (tmp_path / "b.json").write_text(
        json.dumps(
            {
                "request": {"method": "POST", "path": "/b"},
                "response": {"status": 200, "json": {"n": 2}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "request": {"method": "POST", "path": "/a"},
                "response": {"status": 200, "json": {"n": 1}},
            }
        ),
        encoding="utf-8",
    )
    pairs = inference.load_pairs(tmp_path)
    assert [pair["request"]["path"] for pair in pairs] == ["/a", "/b"]


def test_load_pairs_missing_directory(tmp_path: Path) -> None:
    assert inference.load_pairs(tmp_path / "missing") == []
