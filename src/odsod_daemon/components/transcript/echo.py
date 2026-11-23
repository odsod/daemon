"""Pure echo decision using sys coverage, pending utterances, and text."""

from datetime import datetime, timedelta
from typing import Literal

from odsod_daemon.components.transcript.config import TranscriptConfig
from odsod_daemon.lib import clock, textmatch


def overlaps(record: dict, start: datetime, end: datetime) -> bool:
    return (
        clock.parse_iso(record["start"]) < end
        and clock.parse_iso(record["end"]) > start
    )


def decide(
    mic: dict,
    utterances: list[dict],
    texts: list[dict],
    coverage: dict[str, datetime],
    now: datetime,
    config: TranscriptConfig,
) -> Literal["hold", "drop", "keep"]:
    start = clock.parse_iso(mic["start"]) - timedelta(seconds=config.echo_tolerance_s)
    end = clock.parse_iso(mic["end"]) + timedelta(seconds=config.echo_tolerance_s)
    completed = {r["input"] for r in texts}
    waiting = (
        coverage.get("sys") is None
        or coverage["sys"] < end
        or any(
            r["channel"] == "sys"
            and overlaps(r, start, end)
            and r["id"] not in completed
            for r in utterances
        )
    )
    if waiting:
        age = (now - clock.parse_iso(mic["ts"])).total_seconds()
        return "hold" if age < config.echo_hold_max_s else "keep"
    if len(textmatch.normalize(mic["text"]).split()) < 3:
        return "keep"
    matching = sorted(
        (
            r
            for r in texts
            if r["channel"] == "sys"
            and r["outcome"] == "ok"
            and r.get("text")
            and overlaps(r, start, end)
        ),
        key=lambda r: r["start"],
    )
    candidates = [r["text"] for r in matching]
    if candidates:
        candidates.append(" ".join(candidates))
    return (
        "drop"
        if any(
            textmatch.overlap(mic["text"], text) >= config.echo_threshold
            for text in candidates
        )
        else "keep"
    )
