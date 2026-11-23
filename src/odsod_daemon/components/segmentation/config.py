"""The shared speech section and per-channel segmentation settings."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(default=0.5, gt=0, le=1)
    neg_threshold: float = Field(default=0.35, ge=0, le=1)
    min_silence_ms: float = Field(default=500, gt=0)
    min_speech_ms: float = Field(default=250, ge=0)
    pad_start_ms: float = Field(default=300, ge=0)
    pad_end_ms: float = Field(default=400, ge=0)
    max_s: float = Field(default=28, gt=0, le=28)
    idle_close_s: float = Field(default=3, gt=0)
    energy_floor_dbfs: float = -65

    @model_validator(mode="after")
    def thresholds(self):
        if self.neg_threshold > self.threshold:
            raise ValueError("neg_threshold must not exceed threshold")
        return self


class Segmentation(Settings):
    mic: dict[str, float] = Field(default_factory=dict)
    sys: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def overrides(self):
        for channel in ("mic", "sys"):
            self.for_channel(channel)
        return self

    def for_channel(self, channel: str) -> Settings:
        base = self.model_dump(exclude={"mic", "sys"})
        return Settings.model_validate(base | getattr(self, channel))


class Ambient(BaseModel):
    language: str = "auto"
    languages: list[str] = Field(default_factory=lambda: ["sv", "en"])
    fallback_language: str = "sv"


class Dictation(BaseModel):
    presence_threshold: float = Field(default=0.3, ge=0, le=1)
    presence_min_ms: float = Field(default=150, ge=0)
    entropy_thold: float = 2.8
    logprob_thold: float = -1.25
    timeout_s: float = Field(default=8, gt=0)
    cleanup_timeout_ms: float = Field(default=1000, gt=0)


class Speech(BaseModel):
    backend: str = Field(default="whisper", pattern=r"^[a-zA-Z0-9_-]+$")
    prompt_languages: list[str] = Field(default_factory=lambda: ["Swedish", "English"])
    segmentation: Segmentation = Field(default_factory=Segmentation)
    ambient: Ambient = Field(default_factory=Ambient)
    dictation: Dictation = Field(default_factory=Dictation)
    glossary_prompt_chars: int = Field(default=800, ge=0)
    attempts: int = Field(default=3, ge=1)
    phantoms: list[str] = Field(
        default_factory=lambda: ["Thanks for watching", "Tack för att du tittade"]
    )
