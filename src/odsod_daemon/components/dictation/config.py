"""Dictation settings and fixed speech-mask budgets."""

from pydantic import BaseModel, Field

PREROLL = 0.3
POSTROLL = 0.15
MAX_HOLD = 120.0
MUTE_TIMEOUT = 0.15


class DictationConfig(BaseModel):
    text_timeout_s: float = Field(default=10, gt=0)
    restore_delay_ms: int = Field(default=500, ge=0)
    probe_interval_s: float = Field(default=5, gt=0)
