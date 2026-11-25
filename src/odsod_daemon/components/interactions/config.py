"""Interactions settings from ADR-0016."""

from pydantic import BaseModel, Field


class InteractionsConfig(BaseModel):
    # Unknown keys are ignored, so keys of the old LLM summary (`model`,
    # `chunk_chars`, …) in an owner's config.json still load.
    owner_name: str = "Owner"
    owner_aliases: list[str] = []
    silence_cutoff_s: float = Field(default=300, gt=0)
    meeting_cutoffs: dict[str, float] = {}
    skip_max_lines: int = Field(default=3, ge=0)
    speaker_pad_s: float = Field(default=0.5, ge=0)
    echo_threshold: float = Field(default=0.6, ge=0, le=1)
    echo_tolerance_s: float = Field(default=2, ge=0)
    waiting_warn_h: float = Field(default=24, gt=0)
