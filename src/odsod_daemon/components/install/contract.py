"""Models and the shipped-service list for the install component.

A build that adds a service adds its name to SERVICES in the same commit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SERVICES: tuple[str, ...] = ("capture", "pipeline", "tray", "session")

Source = Literal["git", "dev"]


class InstallRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Source
    commit: str
    workspace: str | None = None
    dirty: bool = False
    installed_at: str


class PreviousCommit(BaseModel):
    model_config = ConfigDict(extra="allow")

    commit: str
    source: Source
    replaced_at: str
