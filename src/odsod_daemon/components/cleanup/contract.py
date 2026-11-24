"""Models of what the cleanup component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["ok", "empty", "expired", "failed"]
RawReason = (
    Literal["timeout", "llm-empty", "guard-length", "guard-number", "guard-overlap"]
    | None
)


class TextRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["text"] = "text"
    input: str
    outcome: Outcome
    channel: str | None = None
    start: str | None = None
    end: str | None = None
    text: str | None = None
    language: str | None = None
    raw: bool = False
    raw_reason: RawReason = None
    heard: str | None = None
    setup: str | None = None
    ms: int | None = None
    prompt: str | None = None
    error: str | None = None
