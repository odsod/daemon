"""Publishing settings: the target directories and their document types."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DocumentType = Literal["transcripts", "interactions"]
NAME = re.compile(r"[a-z0-9-]+")


class Target(BaseModel):
    name: str
    dir: Path
    types: list[DocumentType] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not NAME.fullmatch(value):
            raise ValueError("must match [a-z0-9-]+")
        return value

    @field_validator("dir", mode="before")
    @classmethod
    def _expand_home(cls, value: object) -> object:
        return Path(str(value)).expanduser()

    @field_validator("dir")
    @classmethod
    def _check_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("must be an absolute path")
        return value


class PublishingConfig(BaseModel):
    targets: list[Target] = Field(default_factory=list)
    scan_s: float = Field(default=5, gt=0)
    retry_s: float = Field(default=30, gt=0)

    @model_validator(mode="after")
    def _check_unique_names(self) -> PublishingConfig:
        names = [target.name for target in self.targets]
        if len(names) != len(set(names)):
            raise ValueError("target names must be unique")
        return self
