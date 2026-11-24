"""Render immutable interaction documents and their file names."""

import re
import unicodedata
from datetime import tzinfo

import yaml

from odsod_daemon.components.interactions.boundaries import Boundary, Record, at, key
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.contract import (
    InteractionDocument,
    MeetingInfo,
)
from odsod_daemon.components.interactions.summarize import Summary


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
    summary: Summary,
    host: str,
    zone: tzinfo,
    config: InteractionsConfig,
) -> InteractionDocument:
    names = {config.owner_name}
    names.update(line["name"] for line in lines if line["channel"] != "note")
    for event in events:
        if (
            key(event) == key(boundary.meeting)
            and boundary.start <= at(event) <= boundary.end
        ):
            names.update(event.get("names", []))
    meeting = MeetingInfo.model_validate(boundary.meeting) if boundary.meeting else None
    return InteractionDocument(
        id=boundary.id,
        host=host,
        start=boundary.start.astimezone(zone).isoformat(timespec="milliseconds"),
        end=boundary.end.astimezone(zone).isoformat(timespec="milliseconds"),
        timezone=str(zone),
        meeting=meeting,
        participants=sorted(names),
        title=summary.title,
    )


def render(
    meta: InteractionDocument, summary: Summary, lines: list[Record], zone: tzinfo
) -> str:
    points = "\n".join(
        f"- **{p.label}:** "
        + (f"{p.owner}: " if p.label == "Next" and p.owner else "")
        + p.text
        for p in summary.points
    )
    return (
        "---\n"
        + yaml.safe_dump(
            meta.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        )
        + f"---\n\n# {meta.title}\n\n## Summary\n\n{summary.overview}\n\n{points}"
        + "\n\n## Transcript\n\n"
        + transcript(lines, zone, True)
        + "\n"
    )


def filename(meta: InteractionDocument) -> str:
    slug = unicodedata.normalize("NFKD", meta.title).encode("ascii", "ignore").decode()
    slug = (
        re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")[:40].rstrip("-")
        or "interaction"
    )
    stamp = meta.start[:10] + "-" + meta.start[11:16].replace(":", "")
    return f"{stamp}-{meta.host}-{slug}.md"
