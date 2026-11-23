"""Models and constants for the capture component."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

CAPTURE_APP_NAME = "odsod-daemon-capture"
CHANNELS = ("mic", "sys")

Channel = Literal["mic", "sys"]
GapReason = Literal["suspend", "clock", "stall"] | None


class _Record(BaseModel):
    model_config = ConfigDict(extra="allow")


class CaptureStart(_Record):
    ts: str
    kind: Literal["start"] = "start"
    channel: Channel
    audio_start: str
    prev_end: str | None = None


class CaptureStop(_Record):
    ts: str
    kind: Literal["stop"] = "stop"
    channel: Channel
    reason: str | None = None


class CaptureGap(_Record):
    ts: str
    kind: Literal["gap"] = "gap"
    channel: Channel
    start: str
    end: str
    reason: GapReason = None


Record = CaptureStart | CaptureStop | CaptureGap
