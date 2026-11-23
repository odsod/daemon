"""Models of what the pause component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

By = Literal["cli", "tray", "timer", "login"] | None


class PausedFlag(BaseModel):
    model_config = ConfigDict(extra="allow")

    since: str


class PauseRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["pause"] = "pause"
    by: By = None
