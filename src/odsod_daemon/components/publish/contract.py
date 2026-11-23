"""Models of what the publish component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Delivery(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["delivery"] = "delivery"
    document: str
    target: str
    type: Literal["transcripts", "interactions"] | None = None
    bytes: int | None = None
    sha256: str | None = None


class PublishedStart(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["start"] = "start"
    since: str
