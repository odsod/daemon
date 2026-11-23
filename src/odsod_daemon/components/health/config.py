"""Thresholds owned by control."""

from pydantic import BaseModel, ConfigDict, Field


class ControlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tray_interval_s: float = Field(default=1.0, gt=0)
    unit_grace_s: float = Field(default=5, ge=0)
    audio_stale_s: float = Field(default=120, gt=0)
    backlog_warning_s: float = Field(default=600, ge=0)
