"""Render immutable interaction documents and their file names."""

import re
import unicodedata
from datetime import datetime, tzinfo

import yaml

from odsod_daemon.components.interactions.boundaries import Boundary, Record, at, key
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import (
    InteractionDocument,
    MeetingInfo,
)


def transcript(lines: list[Record], zone: tzinfo, markdown: bool = False) -> str:
    result = []
    for line in lines:
        stamp = at(line).astimezone(zone).strftime("%H:%M:%S")
        name = line["name"]
        label = f"**{name}:**" if markdown else f"{name}:"
        prefix = "📝 " if markdown and line["channel"] == "note" else ""
        result.append(
            f"[{stamp}] {prefix}{label} {line['text']}{comment(line, markdown)}"
        )
    return "\n".join(result)


def comment(line: Record, markdown: bool) -> str:
    """The utterance ID, to find its audio, and what ASR heard if cleanup changed it.

    Hidden in rendered Markdown. `--` would end the comment, so it becomes `- -`."""
    if not markdown or line["channel"] == "note" or not line.get("input"):
        return ""
    heard = line.get("heard")
    extra = f" heard: {heard.replace('--', '- -')}" if heard else ""
    return f" <!-- id:{line['input']}{extra} -->"


def metadata(
    boundary: Boundary,
    lines: list[Record],
    events: list[Record],
    host: str,
    zone: tzinfo,
) -> InteractionDocument:
    names = {line["name"] for line in lines if line["channel"] != "note"}
    for event in events:
        if (
            key(event) == key(boundary.meeting)
            and boundary.start <= at(event) <= boundary.end
        ):
            names.update(event.get("names", []))
    # Labels, not people: unknown remote speech and the unset owner name.
    names -= {"Others", InteractionsConfig.model_fields["owner_name"].default}
    meeting = MeetingInfo.model_validate(boundary.meeting) if boundary.meeting else None
    return InteractionDocument(
        id=boundary.id,
        host=host,
        start=(boundary.meeting_start or boundary.start)
        .astimezone(zone)
        .isoformat(timespec="milliseconds"),
        end=boundary.end.astimezone(zone).isoformat(timespec="milliseconds"),
        timezone=str(zone),
        meeting=meeting,
        participants=sorted(names),
        title=(meeting.title.strip() or None) if meeting else None,
    )


def heading(title: str | None, start: datetime, zone: tzinfo) -> str:
    return title or f"Interaction {start.astimezone(zone):%H:%M}"


def render(
    meta: InteractionDocument, heading: str, lines: list[Record], zone: tzinfo
) -> str:
    return (
        "---\n"
        + yaml.safe_dump(
            meta.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        )
        + f"---\n\n# {heading}\n\n## Transcript\n\n"
        + transcript(lines, zone, True)
        + "\n"
    )


def filename(start: datetime, host: str, title: str | None, zone: tzinfo) -> str:
    """`<local day>-<HHMM>-<host>[-<slug>].md`; a title with no ASCII letter
    or digit left gives no slug."""
    slug = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40].rstrip("-")
    name = f"{start.astimezone(zone):%Y-%m-%d-%H%M}-{host}"
    return f"{name}-{slug}.md" if slug else f"{name}.md"
