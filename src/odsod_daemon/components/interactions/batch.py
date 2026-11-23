"""One gated batch pass with crash recovery and ordered writes."""

from collections.abc import Awaitable, Callable
from datetime import tzinfo
from pathlib import Path

from odsod_daemon.components.interactions.boundaries import Boundary, Record
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import (
    FinishedInteraction,
    Interaction,
    MeetingRef,
    parse_front_matter,
)
from odsod_daemon.components.interactions.lines import collect
from odsod_daemon.components.interactions.render import (
    filename,
    metadata,
    render,
    transcript,
)
from odsod_daemon.components.interactions.summarize import Summary
from odsod_daemon.lib import clock, documents, paths, streams


def gate(
    ambient: list[Record],
    dictation: list[Record],
    text: list[Record],
    mains: bool,
    reachable: bool,
) -> bool:
    done = {t["input"] for t in text}
    return mains and reachable and all(u["id"] in done for u in ambient + dictation)


def records(directory: Path) -> list[Record]:
    return [
        r for path in sorted(directory.glob("*.jsonl")) for r in streams.read_day(path)
    ]


def append(directory: Path, record: Record) -> None:
    streams.append(streams.day_path(directory, clock.utc_now().date()), record)


async def process(
    boundary: Boundary,
    text: list[Record],
    events: list[Record],
    config: InteractionsConfig,
    roots: paths.Roots,
    host: str,
    zone: tzinfo,
    summarize: Callable[[str], Awaitable[tuple[Summary, str]]],
) -> None:
    directory = roots.state / "documents/interactions"
    prefix = boundary.start.astimezone(zone).strftime("%Y-%m-%d-%H%M-") + host + "-"
    document = None
    setup = None
    lines = collect(boundary, text, events, config)
    count = sum(line["channel"] != "note" for line in lines)
    for path in sorted(directory.glob(prefix + "*.md")):
        meta = parse_front_matter(documents.read(path))
        if meta.id == boundary.id:
            document = path.name
            break
    outcome = "ok"
    if document is None:
        if count == 0:
            outcome = "skipped"
        else:
            summary, setup = await summarize(transcript(lines, zone))
            if summary.skip and count <= config.skip_max_lines:
                outcome = "skipped"
            else:
                meta = metadata(boundary, lines, events, summary, host, zone, config)
                document = filename(meta)
                base = Path(document).stem
                suffix = 2
                while (directory / document).exists():
                    document = f"{base}-{suffix}.md"
                    suffix += 1
                documents.write(
                    directory / document, render(meta, summary, lines, zone)
                )
    if document is not None:
        finished = roots.state / "finished/interactions"
        if not any(r["id"] == boundary.id for r in records(finished)):
            append(
                finished,
                FinishedInteraction(
                    ts=clock.iso(), id=boundary.id, document=document
                ).model_dump(mode="json"),
            )
    append(
        roots.state / "interactions",
        Interaction(
            ts=clock.iso(),
            id=boundary.id,
            start=clock.iso(boundary.start),
            end=clock.iso(boundary.end),
            outcome=outcome,
            document=document,
            meeting=(
                MeetingRef.model_validate(boundary.meeting)
                if boundary.meeting
                else None
            ),
            end_cause=boundary.end_cause,
            lines=count,
            setup=setup,
        ).model_dump(mode="json"),
    )
