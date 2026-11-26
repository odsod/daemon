"""Models of what this component writes.

Sync copies a satellite's audio, events, dictation utterances and
``run/status.json`` into its host root on the base, byte for byte
(ADR-0024). Its own records are the pause flag ``state/sync-paused`` and
``run/sync.json``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SyncPaused(BaseModel):
    model_config = ConfigDict(extra="allow")

    since: str


class SyncStatus(BaseModel):
    """``run/sync.json``: the end of the last complete pass."""

    model_config = ConfigDict(extra="allow")

    last_ok: str


class SyncResult(BaseModel):
    state: Literal["paused", "running"]
    paused_since: str | None = None
    changed: bool
