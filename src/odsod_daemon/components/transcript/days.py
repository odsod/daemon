"""Pure local-day assignment, coverage advancement, and finish decisions."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from odsod_daemon.components.transcript import gaps
from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.lib import clock


def bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, time.min, zone).astimezone(UTC),
        datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC),
    )


def assigned(record: dict, day: date, zone: ZoneInfo) -> bool:
    return clock.parse_iso(record["start"]).astimezone(zone).date() == day


def missing(
    day: date, zone: ZoneInfo, utterances: list[dict], texts: list[dict]
) -> list[dict]:
    completed = {r["input"] for r in texts}
    return [
        r for r in utterances if r["id"] not in completed and assigned(r, day, zone)
    ]


def finish(
    day: date,
    zone: ZoneInfo,
    now: datetime,
    coverage: dict[str, datetime],
    off: list[gaps.OffRange],
    pending: list[dict],
    held: bool,
    config: TranscriptConfig,
) -> Literal["ready", "cap"] | None:
    start, end = bounds(day, zone)
    if now >= end + timedelta(hours=config.finish_cap_h):
        return "cap"
    if now < end + timedelta(seconds=config.finish_settle_s) or pending or held:
        return None
    for channel in ("mic", "sys"):
        cursor = coverage.get(channel)
        ranges = sorted(
            (r for r in off if channel in r.channels), key=lambda r: r.start
        )
        if cursor is None:
            if not any(r.start <= start <= r.end for r in ranges):
                return None
            cursor = start
        for item in ranges:
            if item.start <= cursor < item.end:
                cursor = item.end
        if cursor < end:
            return None
    return "ready"


def capped_lines(pending: list[dict], zone: ZoneInfo):
    """Merge adjacent pending ranges of each channel before rendering cap loss."""
    from odsod_daemon.components.transcript.lines import untranscribed

    merged: list[dict] = []
    for record in sorted(pending, key=lambda r: (r["channel"], r["start"], r["id"])):
        if (
            merged
            and record["channel"] == merged[-1]["channel"]
            and record["start"] <= merged[-1]["end"]
        ):
            merged[-1]["end"] = max(record["end"], merged[-1]["end"])
        else:
            merged.append(dict(record))
    return [untranscribed(r, zone, "finish-cap") for r in merged]
