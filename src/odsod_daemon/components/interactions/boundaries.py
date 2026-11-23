"""Detect closed interactions from times only."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import EndCause
from odsod_daemon.lib import clock

Record = dict[str, Any]


def at(record: Record) -> datetime:
    return clock.parse_iso(record.get("at", record["ts"]))


def meeting_at(events: list[Record], moment: datetime) -> Record | None:
    meeting = None
    for event in events:
        if at(event) > moment:
            continue
        if event["kind"] == "meeting-start":
            meeting = event
        elif event["kind"] == "meeting-end" and meeting and key(event) == key(meeting):
            meeting = None
    return meeting


def key(meeting: Record | None) -> tuple[str, str] | None:
    return (
        (meeting["platform"], meeting["code"])
        if meeting and "platform" in meeting
        else None
    )


@dataclass
class Boundary:
    id: str
    start: datetime
    end: datetime
    meeting: Record | None
    end_cause: EndCause
    inputs: list[str]


def detect(
    utterances: list[Record],
    events: list[Record],
    coverage: list[Record],
    capture: list[Record],
    now: datetime,
    config: InteractionsConfig,
) -> list[Boundary]:
    events = sorted(events, key=at)
    capture = sorted(capture, key=at)
    off = []
    for i, event in enumerate(capture):
        kind = event["kind"]
        if kind == "start" and event.get("prev_end"):
            off.append(
                (
                    clock.parse_iso(event["prev_end"]),
                    clock.parse_iso(event["audio_start"]),
                    event.get("channel"),
                )
            )
        elif kind == "gap":
            off.append(
                (
                    clock.parse_iso(event["start"]),
                    clock.parse_iso(event["end"]),
                    event.get("channel"),
                )
            )
        elif kind == "stop":
            next_start = next(
                (
                    e
                    for e in capture[i + 1 :]
                    if e["kind"] == "start" and e.get("channel") == event.get("channel")
                ),
                None,
            )
            off.append(
                (
                    at(event),
                    clock.parse_iso(next_start["audio_start"]) if next_start else now,
                    event.get("channel"),
                )
            )
    covered = []
    for channel in ("mic", "sys"):
        end = max(
            (clock.parse_iso(c["end"]) for c in coverage if c["channel"] == channel),
            default=datetime.min.replace(tzinfo=now.tzinfo),
        )
        for start, stop, source_channel in sorted(off):
            if source_channel in (None, channel) and start <= end <= stop:
                end = stop
        covered.append(end)
    horizon = min(covered)
    result = []
    opened: Boundary | None = None

    def cause(boundary: Boundary, until: datetime) -> EndCause:
        changes = [e for e in events if boundary.start < at(e) <= until]
        if any(e["kind"] == "pin" for e in changes):
            return "pin"
        if any(e["kind"] in {"meeting-start", "meeting-end"} for e in changes):
            return "meeting"
        cutoff = config.meeting_cutoffs.get(
            (boundary.meeting or {}).get("code", ""), config.silence_cutoff_s
        )
        return "silence" if (until - boundary.end).total_seconds() >= cutoff else None

    for utterance in sorted(utterances, key=lambda u: (u["start"], u["id"])):
        start, end = map(clock.parse_iso, (utterance["start"], utterance["end"]))
        why = cause(opened, start) if opened else None
        if opened and why:
            opened.end_cause = why
            result.append(opened)
            opened = None
        if opened is None:
            ident = (
                start.strftime("%Y%m%dT%H%M%S.") + f"{start.microsecond // 1000:03d}Z"
            )
            opened = Boundary(ident, start, end, meeting_at(events, start), None, [])
        opened.inputs.append(utterance["id"])
        opened.end = max(opened.end, end)
    if opened and horizon >= opened.end:
        # Only events after the last speech can close the trailing range.
        trailing = [e for e in events if at(e) > opened.end]
        original = events
        events = trailing
        why = cause(opened, horizon)
        events = original
        if why:
            opened.end_cause = why
            result.append(opened)
    return result
