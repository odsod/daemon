"""Models and the shipped-service list for the install component.

A build that adds a service adds its name to SERVICES in the same commit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SERVICES: tuple[str, ...] = ("capture", "pipeline", "tray")

# Package paths whose code the capture service runs. Capture restarts only
# when these change, so a deploy of other code leaves no audio gap. The CLI
# imports every component, but capture runs only this code.
CAPTURE_SCOPE: tuple[str, ...] = (
    "components/capture/",
    "services/capture.py",
    "services/runner.py",
    "lib/",
)

Source = Literal["git", "dev"]


class InstallRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Source
    commit: str
    workspace: str | None = None
    dirty: bool = False
    installed_at: str
    # Digests of the installed code: "capture" over CAPTURE_SCOPE, "all" over
    # the whole package. Empty in records written before hot deploys.
    digests: dict[str, str] = {}


class PreviousCommit(BaseModel):
    model_config = ConfigDict(extra="allow")

    commit: str
    source: Source
    replaced_at: str
