"""Interactions settings from ADR-0016."""

from pydantic import BaseModel, Field


class InteractionsConfig(BaseModel):
    owner_name: str = "Owner"
    owner_aliases: list[str] = []
    languages: list[str] = ["Swedish", "English"]
    silence_cutoff_s: float = Field(default=300, gt=0)
    meeting_cutoffs: dict[str, float] = {}
    model: str = "default"
    chunk_chars: int = Field(default=37000, gt=0)
    request_timeout_s: float = Field(default=600, gt=0)
    max_attempts: int = Field(default=3, ge=1)
    skip_max_lines: int = Field(default=3, ge=0)
    title_max_words: int = Field(default=8, ge=1)
    speaker_pad_s: float = Field(default=0.5, ge=0)
    echo_threshold: float = Field(default=0.6, ge=0, le=1)
    echo_tolerance_s: float = Field(default=2, ge=0)
    waiting_warn_h: float = Field(default=24, gt=0)
    power_check_s: float = Field(default=60, gt=0)
