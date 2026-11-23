"""Models of what the segmentation component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Channel = Literal["mic", "sys"]
CutReason = Literal["pause", "forced", "mask", "end-of-audio"] | None


class _Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class AmbientUtterance(_Record):
    ts: str
    kind: Literal["utterance"] = "utterance"
    id: str
    channel: Channel
    start: str
    end: str
    vad: float | None = None
    cut: CutReason = None


class Covered(_Record):
    ts: str
    kind: Literal["covered"] = "covered"
    channel: Channel
    end: str


Record = AmbientUtterance | Covered
