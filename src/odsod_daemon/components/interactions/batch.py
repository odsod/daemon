"""One gated batch pass with crash recovery and ordered writes."""

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
from odsod_daemon.components.interactions.lines import collect, skip
from odsod_daemon.components.interactions.render import (
    filename,
    heading,
    metadata,
    render,
)
from odsod_daemon.lib import clock, documents, paths, streams


def gate(
    ambient: list[Record],
    dictation: list[Record],
    text: list[Record],
) -> bool:
    done = {t["input"] for t in text}
    return all(u["id"] in done for u in ambient + dictation)


def records(directory: Path) -> list[Record]:
    return [
        r for path in sorted(directory.glob("*.jsonl")) for r in streams.read_day(path)
    ]


def append(directory: Path, record: Record) -> None:
    streams.append(streams.day_path(directory, clock.utc_now().date()), record)


def process(
    boundary: Boundary,
    text: list[Record],
    events: list[Record],
    config: InteractionsConfig,
    roots: paths.Roots,
    host: str,
    zone: tzinfo,
) -> None:
    directory = roots.state / "documents/interactions"
    # Names with and without a slug, and with a `-2` suffix.
    prefix = filename(boundary.start, host, None, zone).removesuffix(".md")
    document = None
    lines = collect(boundary, text, events, config)
    count = sum(line["channel"] != "note" for line in lines)
    for path in sorted(directory.glob(prefix + "*.md")):
        meta = parse_front_matter(documents.read(path))
        if meta.id == boundary.id:
            document = path.name
            break
    outcome = "ok"
    if document is None:
        if skip(lines, config.skip_max_lines):
            outcome = "skipped"
        else:
            meta = metadata(boundary, lines, events, host, zone)
            document = filename(boundary.start, host, meta.title, zone)
            base = Path(document).stem
            suffix = 2
            while (directory / document).exists():
                document = f"{base}-{suffix}.md"
                suffix += 1
            title = heading(meta.title, boundary.start, zone)
            documents.write(directory / document, render(meta, title, lines, zone))
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
        ).model_dump(mode="json"),
    )
