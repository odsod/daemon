"""Load one config section into a model and list errors.

The config file is ``config/config.json``. The top level holds ``common`` and
one section per subsystem. ``lib/`` never imports a section model; the caller
passes it in.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from odsod_daemon.lib import inference, paths


class ConfigError(ValueError):
    """The config file or one of its sections is invalid."""


class InferenceSection(BaseModel):
    whisper_url: str
    llama_url: str
    # Dictation speech-to-text; unset means whisper_url (ADR-0022).
    dictation_url: str | None = None

    @field_validator("whisper_url", "llama_url", "dictation_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return None if value is None else inference.check_url(value)

    def dictation(self) -> str:
        return self.dictation_url or self.whisper_url


class CommonSection(BaseModel):
    host: str = Field(default_factory=socket.gethostname)
    retention_days: int = Field(default=14, ge=1)
    inference: InferenceSection
    # ADR-0024: a satellite sends its audio and events to the base.
    role: Literal["base", "satellite"] = "base"
    # SSH host of the base; required on a satellite.
    base: str | None = None

    @model_validator(mode="after")
    def _check_base(self) -> CommonSection:
        if self.role == "satellite" and not self.base:
            raise ValueError("a satellite needs common.base")
        return self


def host_name(roots: paths.Roots | None = None) -> str:
    """The host whose files are current: a satellite host root, or this host."""
    return paths.current_host() or load_common(roots).host


def _raw(roots: paths.Roots | None = None) -> dict[str, object]:
    config_root = (roots or paths.roots()).config
    path = config_root / "config.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(f"{path}: file not found") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: top level must be an object")
    return value


def _section_raw(raw: Mapping[str, object], name: str, path: Path) -> dict[str, object]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: section {name!r} must be an object")
    return value


def load_common(roots: paths.Roots | None = None) -> CommonSection:
    resolved = roots or paths.roots()
    raw = _raw(resolved)
    return CommonSection.model_validate(
        _section_raw(raw, "common", resolved.config_file)
    )


def section[T: BaseModel](
    name: str,
    model: type[T],
    *,
    roots: paths.Roots | None = None,
) -> T:
    """Load a section into a model. A missing section uses model defaults."""
    resolved = roots or paths.roots()
    raw = _raw(resolved)
    return model.model_validate(_section_raw(raw, name, resolved.config_file))


def check(
    models: Mapping[str, type[BaseModel]],
    *,
    roots: paths.Roots | None = None,
) -> list[str]:
    """Validate ``common`` and every named section. Return all errors."""
    resolved = roots or paths.roots()
    errors: list[str] = []
    try:
        raw = _raw(resolved)
    except ConfigError as error:
        return [str(error)]

    for name, model in (("common", CommonSection), *models.items()):
        try:
            model.model_validate(_section_raw(raw, name, resolved.config_file))
        except ValidationError as error:
            for detail in error.errors():
                where = ".".join(str(part) for part in detail["loc"])
                errors.append(f"{name}.{where}: {detail['msg']}")
        except ConfigError as error:
            errors.append(str(error))
    return errors


def load_sections(
    models: Mapping[str, type[BaseModel]],
    *,
    roots: paths.Roots | None = None,
) -> dict[str, BaseModel]:
    """Load ``common`` and every named section, or raise the first error."""
    resolved = roots or paths.roots()
    loaded: dict[str, BaseModel] = {"common": load_common(resolved)}
    for name, model in models.items():
        loaded[name] = section(name, model, roots=resolved)
    return loaded
