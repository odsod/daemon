"""Pure conversion of speech and event records to transcript lines."""

from zoneinfo import ZoneInfo

from odsod_daemon.components.transcript.contract import Line
from odsod_daemon.lib import clock


def untranscribed(record: dict, zone: ZoneInfo, reason: str | None = None) -> Line:
    start, end = (
        clock.parse_iso(record[key]).astimezone(zone) for key in ("start", "end")
    )
    why = reason or record["outcome"]
    return Line(
        time=start,
        tag="gap",
        key=f"untx:{record.get('input', record.get('id'))}",
        text=f"untranscribed {start:%H:%M:%S}\u2013{end:%H:%M:%S} ({why})",
    )


def from_record(record: dict, zone: ZoneInfo) -> Line | None:
    kind = record["kind"]
    if kind == "text":
        if record["outcome"] in ("failed", "expired"):
            return untranscribed(record, zone)
        if record["outcome"] != "ok" or not (record.get("text") or "").strip():
            return None
        return Line(
            time=clock.parse_iso(record["start"]).astimezone(zone),
            tag=record["channel"],
            text=record["text"],
            key=record["input"],
        )
    at = clock.parse_iso(record.get("at", record["ts"])).astimezone(zone)
    if kind in ("note", "pin"):
        return Line(
            time=at,
            tag="nfo" if kind == "note" else "pin",
            text=record["text"],
            key=f"{kind}:{record['ts']}",
        )
    if kind in ("meeting-start", "meeting-end"):
        source = f"{record['platform']} {record['code']}"
        text = (
            f"started: {record['title']} ({source})"
            if kind == "meeting-start"
            else f"ended: {source}"
        )
        return Line(time=at, tag="mtg", text=text, key=f"mtg:{kind}:{record['ts']}")
    return None
