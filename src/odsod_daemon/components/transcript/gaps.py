"""Pure recording-off ranges, channel merging, causes, and day splitting."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.components.transcript.contract import Line
from odsod_daemon.lib import clock


@dataclass(frozen=True)
class OffRange:
    start: datetime
    end: datetime
    channels: frozenset[str]
    reasons: tuple[str, ...] = ()
    closed: bool = True


def ranges(capture: list[dict], now: datetime) -> list[OffRange]:
    result = []
    ordered = sorted(capture, key=lambda r: r["ts"])
    for record in ordered:
        channel = frozenset([record["channel"]])
        if record["kind"] == "start" and record.get("prev_end"):
            result.append(
                OffRange(
                    clock.parse_iso(record["prev_end"]),
                    clock.parse_iso(record["audio_start"]),
                    channel,
                )
            )
        elif record["kind"] == "gap":
            reason = (record["reason"],) if record.get("reason") else ()
            result.append(
                OffRange(
                    clock.parse_iso(record["start"]),
                    clock.parse_iso(record["end"]),
                    channel,
                    reason,
                )
            )
    for channel in ("mic", "sys"):
        switches = [
            r
            for r in ordered
            if r["channel"] == channel and r["kind"] in ("start", "stop")
        ]
        if switches and switches[-1]["kind"] == "stop":
            result.append(
                OffRange(
                    clock.parse_iso(switches[-1]["ts"]),
                    now,
                    frozenset([channel]),
                    closed=False,
                )
            )
    return sorted((r for r in result if r.end > r.start), key=lambda r: r.start)


def merge(ranges: list[OffRange]) -> list[OffRange]:
    merged: list[OffRange] = []
    for item in sorted(ranges, key=lambda r: r.start):
        if merged and item.start <= merged[-1].end:
            previous = merged.pop()
            merged.append(
                OffRange(
                    previous.start,
                    max(previous.end, item.end),
                    previous.channels | item.channels,
                    previous.reasons + item.reasons,
                    previous.closed and item.closed,
                )
            )
        else:
            merged.append(item)
    return merged


def cause(
    item: OffRange, user: list[dict], capture: list[dict], config: TranscriptConfig
) -> str:
    if any(
        r["kind"] == "pause"
        and -10 <= (clock.parse_iso(r["ts"]) - item.start).total_seconds() <= 5
        for r in user
    ):
        return "pause"
    if item.reasons:
        return item.reasons[0]
    if (item.end - item.start).total_seconds() <= config.restart_max_s:
        return "restart"
    if any(
        r["kind"] == "stop"
        and abs((clock.parse_iso(r["ts"]) - item.start).total_seconds()) <= 5
        for r in capture
    ):
        return "logout"
    return "unknown"


def segments(item: OffRange, zone: ZoneInfo) -> list[OffRange]:
    parts = []
    cursor = item.start
    while cursor < item.end:
        local = cursor.astimezone(zone)
        midnight = datetime.combine(
            local.date() + timedelta(days=1), datetime.min.time(), zone
        )
        midnight = midnight.astimezone(cursor.tzinfo)
        end = min(item.end, midnight)
        parts.append(
            replace(item, start=cursor, end=end, closed=item.closed or end == midnight)
        )
        cursor = end
    return parts


def lines(
    off: list[OffRange],
    user: list[dict],
    capture: list[dict],
    config: TranscriptConfig,
    zone: ZoneInfo,
) -> list[Line]:
    result = []
    for item in merge(off):
        if (item.end - item.start).total_seconds() <= config.gap_min_s:
            continue
        why = cause(item, user, capture, config)
        for part in segments(item, zone):
            if not part.closed:
                continue
            start, end = part.start.astimezone(zone), part.end.astimezone(zone)
            channel = "" if len(part.channels) > 1 else " " + next(iter(part.channels))
            result.append(
                Line(
                    time=start,
                    tag="gap",
                    key=f"gap:{clock.iso(part.start)}",
                    text=(
                        f"not recording{channel} {start:%H:%M:%S}\u2013"
                        f"{end:%H:%M:%S} ({why})"
                    ),
                )
            )
    return result
