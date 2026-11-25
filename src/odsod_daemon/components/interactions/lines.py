"""Select ambient speech and notes, then remove microphone echo."""

from datetime import timedelta

from odsod_daemon.components.interactions.boundaries import Boundary, Record, at
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.speakers import speaker
from odsod_daemon.lib import clock, textmatch


def collect(
    boundary: Boundary,
    text: list[Record],
    events: list[Record],
    config: InteractionsConfig,
) -> list[Record]:
    speech = [
        dict(t)
        for t in text
        if t["input"] in boundary.inputs
        and t["outcome"] == "ok"
        and t.get("channel") in {"mic", "sys"}
        and t.get("text")
    ]
    result = []
    pad = timedelta(seconds=config.echo_tolerance_s)
    for line in speech:
        nearby = " ".join(
            s["text"]
            for s in speech
            if s["channel"] == "sys"
            and clock.parse_iso(s["start"]) <= clock.parse_iso(line["end"]) + pad
            and clock.parse_iso(s["end"]) >= clock.parse_iso(line["start"]) - pad
        )
        if (
            line["channel"] == "mic"
            and textmatch.overlap(line["text"], nearby) >= config.echo_threshold
        ):
            continue
        line["name"] = speaker(line, boundary.meeting, events, config)
        line["at"] = line["start"]
        result.append(line)
    result.extend(
        dict(e, name="Note", channel="note", at=e["ts"])
        for e in events
        if e["kind"] == "note" and boundary.start <= at(e) <= boundary.end
    )
    return sorted(result, key=at)


def skip(lines: list[Record], skip_max_lines: int) -> bool:
    """No document: at most `skip_max_lines` speech lines and no note."""
    notes = sum(line["channel"] == "note" for line in lines)
    return notes == 0 and len(lines) <= skip_max_lines
