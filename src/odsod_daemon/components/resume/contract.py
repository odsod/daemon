"""Models of what the resume component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

By = Literal["cli", "tray", "timer", "login"] | None


class ResumeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["resume"] = "resume"
    by: By = None
