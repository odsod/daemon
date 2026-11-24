"""Models and the shipped-service list for the install component.

A build that adds a service adds its name to SERVICES in the same commit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SERVICES: tuple[str, ...] = ("capture", "pipeline", "tray")

# Where the capture service's code starts. Install follows their
# odsod_daemon imports to find the rest. Capture restarts only when these
# files change, so a deploy of other code leaves no audio gap. The CLI
# imports every component, but capture runs only this code.
CAPTURE_ROOTS: tuple[str, ...] = (
    "components/capture/",
    "services/capture.py",
    "services/runner.py",
)

Source = Literal["git", "dev"]


class InstallRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: Source
    commit: str
    workspace: str | None = None
    dirty: bool = False
    installed_at: str
    # Digests of the installed code: "capture" over capture_files(), "all" over
    # the whole package. Empty in records written before hot deploys.
    digests: dict[str, str] = {}


class PreviousCommit(BaseModel):
    model_config = ConfigDict(extra="allow")

    commit: str
    source: Source
    replaced_at: str
