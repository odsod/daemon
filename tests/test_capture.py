"""Capture runs in its own process with the fake pw-record and pactl."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest

import odsod_daemon
from odsod_daemon.lib import audio, clock, streams

BIN = Path(odsod_daemon.__file__).parent / "components" / "capture" / "tests" / "bin"
ODSODCTL = shutil.which("odsodctl")

CAPTURE = {
    "stall_restart_s": 6.0,
    "stall_error_s": 60.0,
    "mic_silent_s": 60.0,
    "reanchor_ms": 150.0,
    "capture_latency_ms": 0.0,
}


def write_config(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "config.json").write_text(
        json.dumps({"capture": CAPTURE}), encoding="utf-8"
    )


def fake_environment(root: Path) -> dict[str, str]:
    sources = root / "sources.json"
    sources.write_text(json.dumps([{"name": "fake_mic", "mute": False}]))
    environment = dict(os.environ)
    environment.update(
        ODSOD_DAEMON_ROOT=str(root),
        PATH=f"{BIN}:{environment['PATH']}",
        FAKE_PW_RECORD_SCRIPT=json.dumps([{"count": 2_000, "value": 7, "delay": 0.1}]),
        FAKE_PW_RECORD_LOG=str(root / "pw-record.log"),
        FAKE_PACTL_SOURCES=str(sources),
        FAKE_PACTL_EVENTS="[]",
        FAKE_PACTL_LOG=str(root / "pactl.log"),
    )
    return environment


def start(root: Path) -> subprocess.Popen[bytes]:
    assert ODSODCTL is not None
    return subprocess.Popen(
        [ODSODCTL, "run", "capture"],
        env=fake_environment(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    _, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr.decode("utf-8", "replace")


def wait_for(predicate: Callable[[], bool], timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition did not become true")


def records(root: Path, kind: str, channel: str | None = None) -> list[dict]:
    directory = root / "state" / "events" / "capture"
    found: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        found.extend(
            record
            for record in streams.read_day(path)
            if record["kind"] == kind
            and (channel is None or record["channel"] == channel)
        )
    return found


def seconds(text: str) -> float:
    return clock.parse_iso(text).timestamp()


def covered(root: Path, channel: str) -> datetime | None:
    return audio.covered_until(root / "state", channel)


def test_restart_hole_matches_prev_end_and_audio_start(tmp_path: Path) -> None:
    write_config(tmp_path)
    first = start(tmp_path)
    try:
        wait_for(lambda: covered(tmp_path, "mic") is not None)
        time.sleep(1.0)
    finally:
        stop(first)
    before = {name: covered(tmp_path, name) for name in ("mic", "sys")}
    time.sleep(0.5)

    second = start(tmp_path)
    try:
        wait_for(
            lambda: (
                len(records(tmp_path, "start", "mic")) == 2
                and covered(tmp_path, "mic") is not None
            )
        )
        time.sleep(0.3)
    finally:
        stop(second)

    for name in ("mic", "sys"):
        starts = records(tmp_path, "start", name)
        assert len(starts) == 2
        assert starts[1]["prev_end"] is not None
        prev_end = seconds(starts[1]["prev_end"])
        audio_start = seconds(starts[1]["audio_start"])
        previous = before[name]
        assert previous is not None
        assert prev_end == pytest.approx(previous.timestamp(), abs=0.1)
        assert audio_start >= prev_end - 0.001
        assert audio_start - prev_end >= 0.3
        assert len(records(tmp_path, "stop", name)) == 2


def test_capture_writes_audio_without_pipeline_or_inference(tmp_path: Path) -> None:
    write_config(tmp_path)
    process = start(tmp_path)
    try:
        wait_for(lambda: covered(tmp_path, "mic") is not None)
        time.sleep(0.5)
        started = time.monotonic()
        first = {name: covered(tmp_path, name) for name in ("mic", "sys")}
        time.sleep(1.0)
        last = {name: covered(tmp_path, name) for name in ("mic", "sys")}
        elapsed = time.monotonic() - started
    finally:
        stop(process)
        time.sleep(0.1)

    for name in ("mic", "sys"):
        begin = first[name]
        end = last[name]
        assert begin is not None
        assert end is not None
        rate = (end - begin).total_seconds() / elapsed
        assert 0.7 <= rate <= 1.3, (name, rate)
    assert records(tmp_path, "gap") == []
    assert records(tmp_path, "start")
    assert len(records(tmp_path, "stop")) == 2

    log = (tmp_path / "pw-record.log").read_text().splitlines()
    arguments = [json.loads(line) for line in log]
    assert len(arguments) == 2
    names = " ".join(" ".join(args) for args in arguments)
    assert "node.name = odsod-daemon-capture-mic" in names
    assert "node.name = odsod-daemon-capture-sys" in names
    assert "stream.capture.sink = true" in names
    assert "--rate 16000 --channels 1 --format s16 --raw" in " ".join(
        " ".join(args) for args in arguments
    )


def test_health_file_has_no_faults_after_a_clean_stop(tmp_path: Path) -> None:
    write_config(tmp_path)
    process = start(tmp_path)
    try:
        wait_for(lambda: covered(tmp_path, "mic") is not None)
        time.sleep(0.5)
    finally:
        stop(process)
    path = tmp_path / "run" / "health" / "capture.json"
    wait_for(path.exists)
    document = json.loads(path.read_text())
    assert document["service"] == "capture"
    assert document["faults"] == []
    assert set(document) == {"service", "ts", "faults"}
