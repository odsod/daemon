"""Models of what this component writes.

Sync copies a satellite's audio, events, dictation utterances and
``run/status.json`` into its host root on the base, byte for byte
(ADR-0024). Its own record is the pause flag ``state/sync-paused``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SyncPaused(BaseModel):
    model_config = ConfigDict(extra="allow")

    since: str


class SyncResult(BaseModel):
    state: Literal["paused", "running"]
    paused_since: str | None = None
    changed: bool
