"""The evaluated daemon state, read by the tray and odsodctl status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

State = Literal[
    "error", "dictating", "warning", "paused", "mic-muted", "running", "unknown"
]
Severity = Literal["error", "warning", "mark"]
Scope = Literal["user", "system"]
Mode = Literal["idle", "dictating"]
DictationReason = (
    Literal["connected", "paused", "no-inference", "no-socket", "session-down"] | None
)


class Reason(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    severity: Severity
    service: str
    since: str
    message: str
    fix: str | None = None


class ServiceState(BaseModel):
    model_config = ConfigDict(extra="allow")

    unit: str
    scope: Scope
    expected: bool
    active_state: str
    sub_state: str
    since: str


class Backlog(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    seconds: float
    oldest: str | None = None


class DictationState(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    reason: DictationReason = None


class StatusReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: State
    exit_code: int
    reasons: list[Reason] = []
    services: list[ServiceState] = []
    newest_audio: dict[str, str | None] = {}
    backlog: Backlog
    mode: Mode
    dictation: DictationState
    paused_since: str | None = None
    # A satellite's sync to the base; None on a base (ADR-0024).
    sync: Literal["running", "paused"] | None = None
    dev: bool = False
    commit: str | None = None
    workspace: str | None = None
    ts: str
