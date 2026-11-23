"""Models of what the dictation component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

KeysState = Literal["connected", "paused", "no-inference", "no-socket"]
Mode = Literal["idle", "dictating"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class DictationUtterance(_Record):
    ts: str
    kind: Literal["utterance"] = "utterance"
    id: str
    channel: Literal["dic"] = "dic"
    start: str
    end: str
    press: str
    release: str
    muted: int


class StatusDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Mode
    since: str
    keys: KeysState
    audio_start: str | None = None


class MutedStream(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    app: str


class MutedDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    streams: list[MutedStream] = []
