"""Sync settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SyncConfig(BaseModel):
    interval_s: float = Field(default=15, gt=0)
    # A fault after this long with no complete pass.
    behind_after_s: float = Field(default=300, ge=0)
    # The base's state root, relative to its home (ADR-0003 default).
    remote_state: str = ".local/state/odsod-daemon"
