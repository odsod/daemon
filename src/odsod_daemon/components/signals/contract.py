"""Models of what the signals component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Platform = Literal["meet", "teams"]
EndCause = Literal["left", "tab-closed", "restart"] | None


class _Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class MeetingStart(_Record):
    ts: str
    kind: Literal["meeting-start"] = "meeting-start"
    platform: Platform
    code: str
    title: str
    url: str | None = None
    at: str


class MeetingEnd(_Record):
    ts: str
    kind: Literal["meeting-end"] = "meeting-end"
    platform: Platform
    code: str
    at: str
    cause: EndCause = None


class Participants(_Record):
    ts: str
    kind: Literal["participants"] = "participants"
    platform: Platform
    code: str
    names: list[str]


class Speaking(_Record):
    ts: str
    kind: Literal["speaking"] = "speaking"
    platform: Platform
    code: str
    names: list[str]
    at: str


Record = MeetingStart | MeetingEnd | Participants | Speaking
