"""Clients for whisper-server and llama-server, and a replaying fake.

The URL check keeps ambient audio on localhost or the tailnet. The fake serves
recorded request and response pairs on ``127.0.0.1:0``.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import threading
import time
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

WHISPER_PATH = "/v1/audio/transcriptions"
LLAMA_PATH = "/v1/chat/completions"

_TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
_TAILNET_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


class InvalidInferenceURL(ValueError):
    """The URL points somewhere other than localhost or the tailnet."""


def _hostname(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise InvalidInferenceURL(f"{url}: scheme must be http or https")
    if not parts.hostname:
        raise InvalidInferenceURL(f"{url}: missing host")
    return parts.hostname


def is_loopback(url: str) -> bool:
    host = _hostname(url).lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_tailnet(url: str) -> bool:
    host = _hostname(url).lower()
    if host.endswith(".ts.net"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address in _TAILNET_V4 or address in _TAILNET_V6


def check_url(url: str) -> str:
    if not (is_loopback(url) or is_tailnet(url)):
        raise InvalidInferenceURL(
            f"{url}: inference must be on localhost or the tailnet"
        )
    return url


async def reachable(url: str, timeout_s: float) -> bool:
    """A TCP connect with a timeout."""
    parts = urlsplit(url)
    if not parts.hostname:
        return False
    port = parts.port or (443 if parts.scheme == "https" else 80)
    import asyncio

    try:
        async with asyncio.timeout(timeout_s):
            _, writer = await asyncio.open_connection(parts.hostname, port)
    except OSError, TimeoutError:
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


class WhisperResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    language: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class _Choice(BaseModel):
    message: ChatMessage


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    choices: list[_Choice]


class WhisperClient:
    def __init__(self, url: str, *, timeout_s: float = 60.0) -> None:
        self.url = check_url(url)
        self.timeout_s = timeout_s

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.wav",
        fields: Mapping[str, str] | None = None,
    ) -> WhisperResponse:
        data = dict(fields or {})
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                self.url,
                files={"file": (filename, audio, "audio/wav")},
                data=data,
            )
            response.raise_for_status()
            return WhisperResponse.model_validate(response.json())


class LlamaClient:
    def __init__(
        self,
        url: str,
        *,
        model: str = "default",
        timeout_s: float = 180.0,
    ) -> None:
        self.url = check_url(url)
        self.model = model
        self.timeout_s = timeout_s

    async def complete(
        self,
        messages: Sequence[ChatMessage | Mapping[str, str]],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                message.model_dump()
                if isinstance(message, ChatMessage)
                else dict(message)
                for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
            parsed = ChatResponse.model_validate(response.json())
        return parsed.choices[0].message.content


class ReplayServer:
    """A stdlib HTTP server that replays recorded pairs in file order."""

    def __init__(self, pairs: Sequence[Mapping[str, Any]]) -> None:
        self.pairs = [dict(pair) for pair in pairs]
        self.requests: list[dict[str, Any]] = []
        self._used: set[int] = set()
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)

    def _next_pair(self, method: str, path: str) -> Mapping[str, Any] | None:
        with self._lock:
            for index, pair in enumerate(self.pairs):
                if index in self._used:
                    continue
                request = pair.get("request", {})
                if request.get("method", method) != method:
                    continue
                if request.get("path", path) != path:
                    continue
                self._used.add(index)
                return pair
        return None

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def _reply(self, method: str) -> None:
                length = int(self.headers.get("content-length", "0"))
                body = self.rfile.read(length) if length else b""
                path = urlsplit(self.path).path
                with server._lock:
                    server.requests.append(
                        {"method": method, "path": path, "body": body}
                    )
                pair = server._next_pair(method, path)
                if pair is None:
                    self.send_response(500)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":"no replay pair"}')
                    return
                response = pair.get("response", {})
                delay_ms = int(response.get("delay_ms", 0))
                if delay_ms:
                    time.sleep(delay_ms / 1000)
                status = int(response.get("status", 200))
                self.send_response(status)
                headers = response.get("headers", {})
                if not isinstance(headers, Mapping):
                    headers = {}
                lower_names = {str(name).lower() for name in headers}
                for name, value in headers.items():
                    self.send_header(str(name), str(value))
                if "json" in response:
                    payload = json.dumps(response["json"]).encode("utf-8")
                    if "content-type" not in lower_names:
                        self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    payload = str(response.get("body", "")).encode("utf-8")
                    if "content-type" not in lower_names:
                        self.send_header("content-type", "text/plain")
                    self.send_header("content-length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

            def do_POST(self) -> None:
                self._reply("POST")

            def do_GET(self) -> None:
                self._reply("GET")

        return Handler


def load_pairs(directory: Path) -> list[dict[str, Any]]:
    """Load one recorded pair per JSON file, in file name order."""
    if not directory.is_dir():
        return []
    pairs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            pairs.extend(value)
        else:
            pairs.append(value)
    return pairs


def replay_server(directory: Path) -> ReplayServer:
    return ReplayServer(load_pairs(directory))
