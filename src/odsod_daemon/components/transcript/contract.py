"""Models of what the transcript component writes.

The daily transcript is Markdown; this module holds its finished record.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from odsod_daemon.components.transcript.config import local_zone

DOCUMENT_TYPE = "transcripts"


class FinishedTranscript(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["finished"] = "finished"
    document: str
    type: Literal["transcripts"] = DOCUMENT_TYPE
    day: str
    capped: bool = False


class Line(BaseModel):
    time: datetime
    tag: Literal["mic", "sys", "dic", "nfo", "pin", "mtg", "gap"]
    text: str
    key: str

    def render(self) -> str:
        text = " ".join(self.text.split()).replace("<!--", "&lt;!--")
        if any(c in self.key for c in "\r\n<>"):
            raise ValueError("line key contains a line break or HTML delimiter")
        return (
            f"[{self.time:%H:%M:%S}] {EMOJI[self.tag]} **{self.tag}** "
            f"{text} <!-- id:{self.key} -->"
        )


EMOJI = {
    "mic": "🎤",
    "sys": "🔊",
    "dic": "⌨️",
    "nfo": "📝",
    "pin": "📍",
    "mtg": "🪟",
    "gap": "⏸️",
}
_LINE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\] (.+?) \*\*(\w+)\*\* (.*?) <!-- id:(.*?) -->$"
)


def parse_line(text: str, day: date, zone: ZoneInfo) -> Line | None:
    match = _LINE.fullmatch(text)
    if match is None:
        return None
    moment, emoji, tag, content, key = match.groups()
    if EMOJI.get(tag) != emoji:
        return None
    return Line.model_validate(
        {
            "time": datetime.combine(day, time.fromisoformat(moment), zone),
            "tag": tag,
            "text": content,
            "key": key,
        }
    )


def parse_file(text: str) -> list[Line]:
    """Parse complete transcript lines with the day and zone from the header."""
    header = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if header is None:
        return []
    fields = dict(
        line.split(": ", 1) for line in header[1].splitlines() if ": " in line
    )
    day = date.fromisoformat(fields["date"])
    name = fields["timezone"]
    zone = local_zone() if name == "local" else ZoneInfo(name)
    return [
        line
        for raw in text.splitlines(keepends=True)
        if raw.endswith("\n")
        if (line := parse_line(raw.rstrip("\n"), day, zone)) is not None
    ]
