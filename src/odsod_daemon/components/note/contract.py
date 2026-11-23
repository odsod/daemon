"""Models of what the note component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Note(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["note"] = "note"
    text: str
