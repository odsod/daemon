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

Key = Literal["recording", "sync"]


@dataclass(frozen=True)
class Line:
    text: str


@dataclass(frozen=True)
class Toggle:
    """A checkable item: the check shows the state, a click flips it."""

    key: Key
    text: str
    checked: bool


@dataclass(frozen=True)
class Model:
    lines: tuple[Line, ...]
    toggles: tuple[Toggle, ...]


def label(state: State) -> str:
    return LABELS[state]


def local_time(value: str) -> str:
    return clock.parse_iso(value).astimezone().strftime("%Y-%m-%d %H:%M")


def icon_path(report: StatusReport) -> Path:
    """Unknown means the service states are unreadable: show Error."""
    state = "error" if report.state == "unknown" else report.state
    suffix = "-dev" if report.dev else ""
    return ICONS / f"{state}{suffix}.svg"


def tooltip(report: StatusReport) -> str:
    title = label(report.state)
    if not report.reasons:
        return title
    return f"{title}: {report.reasons[0].message}"


def short_time(value: str, now: str) -> str:
    """HH:MM today, with the date on another day."""
    at, today = clock.parse_iso(value).astimezone(), clock.parse_iso(now).astimezone()
    return at.strftime("%H:%M" if at.date() == today.date() else "%Y-%m-%d %H:%M")


def ago(value: str, now: str) -> str:
    """Coarse, so an open menu does not change each second."""
    seconds = (clock.parse_iso(now) - clock.parse_iso(value)).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    return f"{int(seconds // 3600)} h ago"


def toggles(report: StatusReport) -> tuple[Toggle, ...]:
    recording = "Recording"
    if report.paused_since:
        recording += f" · paused since {short_time(report.paused_since, report.ts)}"
    result = [Toggle("recording", recording, report.paused_since is None)]
    # Only a satellite syncs (ADR-0024).
    if report.sync is not None:
        sync = f"Sync to {report.base or 'base'}"
        paused = next(
            (r.since for r in report.reasons if r.code == "sync-paused"), None
        )
        if report.sync == "paused":
            sync += (
                f" · paused since {short_time(paused, report.ts)}"
                if paused
                else " · paused"
            )
        elif report.last_sync:
            sync += f" · {ago(report.last_sync, report.ts)}"
        result.append(Toggle("sync", sync, report.sync == "running"))
    return tuple(result)


def build(report: StatusReport) -> Model:
    lines = []
    for reason in report.reasons:
        # The sync toggle shows the pause.
        if reason.code == "sync-paused":
            continue
        parts = [reason.message, f"Since {local_time(reason.since)}."]
        if reason.fix:
            parts.append(reason.fix)
        lines.append(Line(" ".join(parts)))
    if not report.dictation.available:
        reason = report.dictation.reason or "session-down"
        lines.append(Line(f"Dictation unavailable: {reason}."))
    return Model(tuple(lines), toggles(report))


def command(toggle: Toggle) -> list[str]:
    """The odsodctl command that flips the toggle."""
    if toggle.key == "sync":
        return ["sync", "pause" if toggle.checked else "resume"]
    return ["pause" if toggle.checked else "resume", "--by", "tray"]
