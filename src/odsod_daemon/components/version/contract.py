"""Models of what the version component writes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class VersionReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Literal["git", "dev"]
    commit: str
    workspace: str | None = None
    dirty: bool = False
