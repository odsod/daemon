"""Models of what the interactions component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["ok", "skipped", "failed"]
EndCause = Literal["silence", "meeting", "pin"] | None


class MeetingRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    platform: str
    code: str


class MeetingInfo(MeetingRef):
    title: str


class Interaction(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["interaction"] = "interaction"
    id: str
    start: str
    end: str
    outcome: Outcome
    document: str | None = None
    meeting: MeetingRef | None = None
    error: str | None = None
    end_cause: EndCause = None
    lines: int | None = None
    setup: str | None = None


class FinishedInteraction(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["finished"] = "finished"
    document: str
    type: Literal["interactions"] = "interactions"
    id: str


class InteractionDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["interaction"] = "interaction"
    id: str
    host: str
    start: str
    end: str
    timezone: str
    meeting: MeetingInfo | None = None
    participants: list[str] = []
    title: str
