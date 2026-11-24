"""Shared test fixtures: temp root, fake inference servers, fake systemd, and a
local file server for pinned downloads."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from odsod_daemon.lib import inference, systemd

INFERENCE_TESTDATA = (
    Path(__file__).parent / "src" / "odsod_daemon" / "lib" / "inference" / "testdata"
)


@pytest.fixture
def temp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    for name in ("state", "run", "config"):
        (root / name).mkdir(parents=True)
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(root))
    monkeypatch.setenv("XDG_STATE_HOME", str(root / "xdg-state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "xdg-config"))
    return root


class FakeInference:
    def __init__(self, whisper: inference.ReplayServer, llama: inference.ReplayServer):
        self.whisper = whisper
        self.llama = llama
        self.whisper_url = whisper.url + inference.WHISPER_PATH
        self.llama_url = llama.url + inference.LLAMA_PATH


@pytest.fixture
def fake_inference() -> Iterator[FakeInference]:
    whisper = inference.replay_server(INFERENCE_TESTDATA)
    llama = inference.replay_server(INFERENCE_TESTDATA)
    try:
        yield FakeInference(whisper, llama)
    finally:
        whisper.close()
        llama.close()


@pytest.fixture
def fake_systemd() -> systemd.FakeUnitStates:
    return systemd.FakeUnitStates()


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


class FileServer:
    """Serve files by name on 127.0.0.1; a missing name is a 404."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.gets: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                name = self.path.rsplit("/", 1)[-1]
                outer.gets.append(name)
                data = outer.files.get(name)
                self.send_response(200 if data is not None else 404)
                self.send_header("content-length", str(len(data or b"")))
                self.end_headers()
                self.wfile.write(data or b"")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/rev"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def file_server() -> Iterator[FileServer]:
    server = FileServer()
    try:
        yield server
    finally:
        server.close()
