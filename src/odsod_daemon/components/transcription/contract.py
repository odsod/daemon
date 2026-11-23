"""Models of what the transcription component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["ok", "empty", "expired", "failed"]


class AsrRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["asr"] = "asr"
    input: str
    outcome: Outcome
    text: str | None = None
    language: str | None = None
    setup: str | None = None
    ms: int | None = None
    channel: str | None = None
    start: str | None = None
    end: str | None = None
    attempts: int | None = None
    gate: float | None = None
    error: str | None = None
