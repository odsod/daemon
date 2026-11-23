"""Models of what the pin component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Pin(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["pin"] = "pin"
    text: str = ""
