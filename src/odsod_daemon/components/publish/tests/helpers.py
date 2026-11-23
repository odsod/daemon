"""Shared helpers for publish tests: a fake clock, documents and streams."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from odsod_daemon.components.publish.config import PublishingConfig
from odsod_daemon.components.publish.service import Publisher
from odsod_daemon.lib import clock, config, streams


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)

    def utc_now(self) -> datetime:
        return self.now

    def mono(self) -> float:
        return self.now.timestamp()

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def publishing(root: Path, targets: list[dict], **settings) -> PublishingConfig:
    (root / "config/config.json").write_text(
        json.dumps({"publishing": {"targets": targets, **settings}})
    )
    return config.section("publishing", PublishingConfig)


def target(name: str, directory: Path, types: list[str] | None = None) -> dict:
    return {
        "name": name,
        "dir": str(directory),
        "types": ["transcripts", "interactions"] if types is None else types,
    }


def document(root: Path, name: str, type_: str, text: str) -> Path:
    path = root / "state/documents" / type_ / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def finished(root: Path, name: str, type_: str, at: datetime) -> None:
    source = "transcript" if type_ == "transcripts" else "interactions"
    streams.append(
        streams.day_path(root / "state/finished" / source, at.date()),
        {
            "ts": clock.iso(at),
            "kind": "finished",
            "document": name,
            "type": type_,
        },
    )


def finish(
    root: Path, name: str, type_: str, at: datetime, text: str = "text\n"
) -> Path:
    path = document(root, name, type_, text)
    finished(root, name, type_, at)
    return path


def published(root: Path, name: str) -> list[dict]:
    directory = root / "state/published" / name
    return [
        record
        for path in sorted(directory.glob("*.jsonl"))
        for record in streams.read_day(path)
    ]


def deliveries(root: Path, name: str) -> list[dict]:
    return [record for record in published(root, name) if record["kind"] == "delivery"]


def faults(root: Path) -> list[dict]:
    path = root / "run/health/pipeline.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())["faults"]


def publisher(settings: PublishingConfig, now: datetime) -> Publisher:
    return Publisher(settings, now=now)


def scan(pub: Publisher, now: datetime) -> None:
    pub.scan(now=now, mono=now.timestamp())
