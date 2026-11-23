"""Shared test fixtures: temp root, fake inference servers, fake systemd."""

from __future__ import annotations

from collections.abc import Iterator
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
