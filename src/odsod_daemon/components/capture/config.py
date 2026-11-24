"""The ``capture`` config section (ADR-0011)."""

from __future__ import annotations

from pydantic import BaseModel


class CaptureConfig(BaseModel):
    stall_restart_s: float = 10.0
    stall_error_s: float = 60.0
    mic_silent_s: float = 5.0
    reanchor_ms: float = 150.0
    capture_latency_ms: float = 0.0
