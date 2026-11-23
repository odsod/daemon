"""Fixtures for the bench component tests."""

from __future__ import annotations

import json
import wave
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from odsod_daemon.lib import audio, clock, inference, streams

DATA = Path(__file__).parent / "testdata"
WHISPER = "http://localhost:8178" + inference.WHISPER_PATH
LLAMA = "http://localhost:8179" + inference.LLAMA_PATH


def config(
    root: Path, extra: dict | None = None, *, speech: dict | None = None
) -> dict:
    value = {
        "common": {
            "host": "test-host",
            "inference": {"whisper_url": WHISPER, "llama_url": LLAMA},
        },
        "speech": speech or {},
    }
    value.update(extra or {})
    (root / "config/config.json").write_text(json.dumps(value))
    return value


@pytest.fixture
def bench_root(temp_root: Path) -> Path:
    config(temp_root)
    return temp_root


def write_audio(
    root: Path, channel: str, name: str = "sv-udhr-article1", *, start: datetime | None
):
    """Write a fixture clip into the hourly buffer. Return its range."""
    with wave.open(str(DATA / f"{name}.wav")) as handle:
        pcm = handle.readframes(handle.getnframes())
    begin = start or audio.hour_start(clock.utc_now())
    path = audio.hour_file(root / "state", channel, begin)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm)
    return begin, begin + timedelta(seconds=len(pcm) / audio.BYTES_PER_SECOND)


def add_utterance(
    root: Path,
    *,
    ident: str,
    channel: str,
    start: datetime,
    end: datetime,
    directory: str = "utterances/ambient",
) -> dict:
    record = {
        "ts": clock.iso(end),
        "kind": "utterance",
        "id": ident,
        "channel": channel,
        "start": clock.iso(start),
        "end": clock.iso(end),
    }
    streams.append(streams.day_path(root / "state" / directory, start.date()), record)
    return record


def add_text(
    root: Path,
    record: dict,
    *,
    text: str = "Ett test.",
    language: str = "sv",
    outcome: str = "ok",
    setup: str = "asr-setup",
    ms: int = 100,
) -> None:
    streams.append(
        streams.day_path(root / "state/text", clock.parse_iso(record["start"]).date()),
        {
            "ts": clock.iso(),
            "kind": "text",
            "input": record["id"],
            "outcome": outcome,
            "channel": record["channel"],
            "start": record["start"],
            "end": record["end"],
            "text": text,
            "language": language,
            "raw": False,
            "setup": setup,
            "ms": ms,
        },
    )


def add_asr(
    root: Path,
    record: dict,
    *,
    text: str = "Ett test",
    outcome: str = "ok",
    backend: str = "whisper",
    setup: str = "asr-setup",
    ms: int = 80,
) -> None:
    streams.append(
        streams.day_path(
            root / "state/asr" / backend, clock.parse_iso(record["start"]).date()
        ),
        {
            "ts": clock.iso(),
            "kind": "asr",
            "input": record["id"],
            "outcome": outcome,
            "text": text,
            "language": "sv",
            "setup": setup,
            "ms": ms,
        },
    )


def add_interaction(
    root: Path,
    start: datetime,
    end: datetime,
    *,
    ident: str = "int-1",
    document: str = "20261123-1200-test-host.md",
) -> dict:
    record = {
        "ts": clock.iso(end),
        "kind": "interaction",
        "id": ident,
        "start": clock.iso(start),
        "end": clock.iso(end),
        "outcome": "ok",
        "document": document,
    }
    streams.append(streams.day_path(root / "state/interactions", start.date()), record)
    (root / "state/documents/interactions").mkdir(parents=True, exist_ok=True)
    (root / "state/documents/interactions" / document).write_text("# Meeting\n")
    return record
