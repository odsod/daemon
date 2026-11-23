"""Assign the name with the greatest speaking overlap."""

from datetime import timedelta

from odsod_daemon.components.interactions.boundaries import Record, at, key
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.lib import clock


def speaker(
    line: Record,
    meeting: Record | None,
    events: list[Record],
    config: InteractionsConfig,
) -> str:
    if line["channel"] == "mic":
        return config.owner_name
    if not meeting:
        return "Others"
    start = clock.parse_iso(line["start"]) - timedelta(seconds=config.speaker_pad_s)
    end = clock.parse_iso(line["end"]) + timedelta(seconds=config.speaker_pad_s)
    changes = sorted(
        (
            e
            for e in events
            if e["kind"] in {"speaking", "meeting-end"}
            and key(e) == key(meeting)
            and at(e) >= at(meeting)
        ),
        key=at,
    )
    totals: dict[str, float] = {}
    excluded = {n.casefold() for n in [config.owner_name, *config.owner_aliases]}
    for i, event in enumerate(changes):
        stop = at(changes[i + 1]) if i + 1 < len(changes) else end
        overlap = max(0.0, (min(end, stop) - max(start, at(event))).total_seconds())
        for name in event.get("names", []):
            if name.casefold() not in excluded:
                totals[name] = totals.get(name, 0) + overlap
    return max(
        (n for n in totals if totals[n] > 0), key=lambda n: totals[n], default="Others"
    )
