"""Present one report as a tooltip, an icon and menu lines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from odsod_daemon.components.health.contract import State, StatusReport
from odsod_daemon.lib import clock

ICONS = Path(__file__).with_name("icons")

LABELS: dict[State, str] = {
    "error": "Error",
    "dictating": "Dictating",
    "warning": "Warning",
    "paused": "Paused",
    "mic-muted": "Mic muted",
    "running": "Running",
    "unknown": "Unknown",
}

Action = Literal["pause", "resume"]


@dataclass(frozen=True)
class Line:
    text: str


@dataclass(frozen=True)
class Model:
    lines: tuple[Line, ...]
    action: Action


def label(state: State) -> str:
    return LABELS[state]


def local_time(value: str) -> str:
    return clock.parse_iso(value).astimezone().strftime("%Y-%m-%d %H:%M")


def icon_path(report: StatusReport) -> Path:
    suffix = "-dev" if report.dev else ""
    return ICONS / f"{report.state}{suffix}.svg"


def tooltip(report: StatusReport) -> str:
    title = label(report.state)
    if not report.reasons:
        return title
    return f"{title}: {report.reasons[0].message}"


def build(report: StatusReport) -> Model:
    lines = []
    for reason in report.reasons:
        parts = [reason.message, f"Since {local_time(reason.since)}."]
        if reason.fix:
            parts.append(reason.fix)
        lines.append(Line(" ".join(parts)))
    if not report.dictation.available:
        reason = report.dictation.reason or "session-down"
        lines.append(Line(f"Dictation unavailable: {reason}."))
    action: Action = "resume" if report.paused_since else "pause"
    return Model(tuple(lines), action)
