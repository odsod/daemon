"""Models of what the bench component writes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

CaseKind = Literal["ambient", "dictation", "interaction"]
Outcome = Literal["ok", "empty", "failed"]


class BenchCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    kind: CaseKind
    host: str
    channel: str | None = None
    start: str
    end: str
    language: str | None = None
    source_id: str
    created: str
    commit: str | None = None


class ModelRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    revision: str | None = None


class SetupManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    kind: Literal["asr", "pipeline"]
    model: ModelRef
    llm: ModelRef | None = None
    prompt_sha256: str | None = None
    glossary_sha256: str | None = None
    settings: dict[str, Any] = {}
    commit: str | None = None
    fingerprint: str


class BenchResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    setup: SetupManifest
    outcome: Outcome
    output: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    ts: str


class Review(BaseModel):
    model_config = ConfigDict(extra="allow")

    state: Literal["draft", "accepted"]
    drafted_by: str | None = None
    accepted_by: str | None = None
    accepted_at: str | None = None
    reference_sha256: str | None = None


class LiveAsr(BaseModel):
    model_config = ConfigDict(extra="allow")

    backend: str
    setup: str | None = None
    text: str | None = None
    ms: int | None = None


class Live(BaseModel):
    """What the live pass gave for one case."""

    model_config = ConfigDict(extra="allow")

    asr: list[LiveAsr] = []
    text: str | None = None
    raw: bool = False
    setup: str | None = None
    ms: int | None = None
    ready_ms: int | None = None


class ReportRow(BaseModel):
    """One measure for one group and one setup."""

    model_config = ConfigDict(extra="allow")

    measure: Literal["wer", "glossary", "latency"]
    group: str
    setup: str
    fingerprint: str
    accepted: int
    draft: int
    failed: int
    score: float | None
    unit: Literal["%", "ms"]
    target: float | None
    criterion: str
    label: str = ""
    detail: dict[str, float] = {}
