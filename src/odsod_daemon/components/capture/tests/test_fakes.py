"""The fake ``pw-record`` and ``pactl`` scripts answer as the tests expect."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

BIN = Path(__file__).parent / "bin"
PACTL = BIN / "pactl"


def _env(**values: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(values)
    return env


def test_fake_pw_record_writes_scripted_pcm(tmp_path: Path) -> None:
    log = tmp_path / "log"
    result = subprocess.run(
        [str(BIN / "pw-record"), "--rate", "16000", "-"],
        env=_env(
            FAKE_PW_RECORD_SCRIPT=json.dumps(
                [{"count": 2, "value": 7, "delay": 0}, {"exit": 0}]
            ),
            FAKE_PW_RECORD_LOG=str(log),
        ),
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert result.stdout == (7).to_bytes(2, "little") * 3_200
    assert json.loads(log.read_text().splitlines()[0]) == ["--rate", "16000", "-"]


def test_fake_pactl_reports_the_default_source_and_mute(tmp_path: Path) -> None:
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([{"name": "fake_mic", "mute": True}]))
    env = _env(FAKE_PACTL_SOURCES=str(sources))
    default = subprocess.run(
        [str(PACTL), "--format=json", "get-default-source"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert default.stdout.strip() == "fake_mic"
    listing = subprocess.run(
        [str(PACTL), "--format=json", "list", "sources"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert json.loads(listing.stdout)[0]["mute"] is True


def test_fake_pactl_subscribe_prints_events() -> None:
    process = subprocess.Popen(
        [str(PACTL), "subscribe"],
        env=_env(
            FAKE_PACTL_EVENTS=json.dumps(["Event 'change' on source #1"]),
            FAKE_PACTL_EVENT_DELAY="0",
        ),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "Event 'change' on source #1"
    finally:
        process.terminate()
        process.wait(timeout=10)
