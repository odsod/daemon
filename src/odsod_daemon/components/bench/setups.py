"""Setup config, manifest and fingerprint (ADR-0019)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from odsod_daemon.components.bench.contract import CaseKind, ModelRef, SetupManifest
from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.lib import inference, paths

LIVE_AMBIENT_PROMPT = "cleanup"
LIVE_DICTATION_PROMPT = "cleanup-dictation"


class AsrSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    whisper_url: str | None = None
    model: str
    revision: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("whisper_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return None if value is None else inference.check_url(value)


class CleanupSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llama_url: str | None = None
    model: str
    revision: str | None = None
    ambient_prompt: str | None = None
    dictation_prompt: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("llama_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        return None if value is None else inference.check_url(value)


class Setup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["asr", "pipeline"]
    cases: list[CaseKind] = Field(default_factory=lambda: ["ambient", "dictation"])
    asr: AsrSetup
    cleanup: CleanupSetup | None = None


class CaseTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambient_per_language: int = Field(default=50, ge=0)
    dictation: int = Field(default=50, ge=0)
    interactions: int = Field(default=10, ge=0)
    min_s: float = Field(default=2, ge=0)
    max_s: float = Field(default=30, gt=0)
    max_interaction_min: float = Field(default=60, gt=0)
    max_per_hour: int = Field(default=3, ge=1)
    seed: int = 0


class Bench(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: CaseTargets = Field(default_factory=CaseTargets)
    setups: list[Setup] = Field(default_factory=list)

    def setup(self, name: str) -> Setup:
        for setup in self.setups:
            if setup.name == name:
                return setup
        known = ", ".join(setup.name for setup in self.setups) or "none"
        raise KeyError(f"{name}: unknown setup (known: {known})")


def merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge two dicts key by key, nests included."""
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = merge(current, value)
        else:
            merged[key] = value
    return merged


def host_config(roots: paths.Roots) -> dict[str, Any]:
    path = roots.config_file
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def host_speech(roots: paths.Roots) -> dict[str, Any]:
    section = host_config(roots).get("speech", {})
    return section if isinstance(section, dict) else {}


def speech_settings(setup: Setup, roots: paths.Roots) -> dict[str, Any]:
    """The host ``speech`` section with the setup overrides applied."""
    settings = merge(host_speech(roots), setup.asr.settings)
    if setup.kind == "pipeline" and setup.cleanup is not None:
        settings = merge(settings, setup.cleanup.settings)
    return settings


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def glossary_sha256(roots: paths.Roots) -> str:
    path = roots.config / "glossary.txt"
    return _digest(path.read_bytes() if path.exists() else b"")


def prompt_files(setup: Setup) -> dict[str, str]:
    """The prompt name of each lane, empty for an ``asr`` setup."""
    if setup.kind != "pipeline":
        return {}
    cleanup = setup.cleanup
    ambient = LIVE_AMBIENT_PROMPT
    dictation = LIVE_DICTATION_PROMPT
    if cleanup is not None:
        ambient = cleanup.ambient_prompt or ambient
        dictation = cleanup.dictation_prompt or dictation
    return {"ambient": ambient, "dictation": dictation}


def prompt_sha256(setup: Setup, roots: paths.Roots) -> str | None:
    """Hash of both prompt files of the setup, or None for ``asr``."""
    files = prompt_files(setup)
    if not files:
        return None
    parts = {}
    for lane, name in files.items():
        path = roots.config / "prompts" / f"{name}.md"
        content = path.read_bytes() if path.exists() else b"builtin"
        parts[lane] = {"name": name, "sha256": _digest(content)}
    return _digest(_canonical(parts).encode("utf-8"))


def commit(roots: paths.Roots) -> str:
    path = roots.state / "install/current"
    if not path.exists():
        return "unknown"
    return InstallRecord.model_validate_json(path.read_text()).commit


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def manifest(setup: Setup, roots: paths.Roots) -> SetupManifest:
    """The full setup manifest, with the fingerprint over every field but name."""
    model = ModelRef(name=setup.asr.model, revision=setup.asr.revision)
    llm = None
    if setup.kind == "pipeline" and setup.cleanup is not None:
        llm = ModelRef(name=setup.cleanup.model, revision=setup.cleanup.revision)
    fields = {
        "kind": setup.kind,
        "model": model.model_dump(),
        "llm": None if llm is None else llm.model_dump(),
        "prompt_sha256": prompt_sha256(setup, roots),
        "glossary_sha256": glossary_sha256(roots),
        "settings": speech_settings(setup, roots),
        "commit": commit(roots),
    }
    return SetupManifest(
        name=setup.name,
        kind=setup.kind,
        model=model,
        llm=llm,
        prompt_sha256=fields["prompt_sha256"],
        glossary_sha256=fields["glossary_sha256"],
        settings=fields["settings"],
        commit=fields["commit"],
        fingerprint=_digest(_canonical(fields).encode("utf-8"))[:16],
    )


def live_fingerprint(asr: str | None, text: str | None) -> str:
    return f"live-{asr or 'none'}-{text or 'none'}"


def live_manifest(
    roots: paths.Roots, asr: str | None, text: str | None, *, cleaned: bool
) -> SetupManifest:
    """A manifest for the live pass. Its commit is unknown (ADR-0019)."""
    return SetupManifest(
        name="live",
        kind="pipeline" if cleaned else "asr",
        model=ModelRef(name=asr or "unknown"),
        llm=None if text is None else ModelRef(name=text),
        glossary_sha256=glossary_sha256(roots),
        commit=None,
        fingerprint=live_fingerprint(asr, text),
    )
