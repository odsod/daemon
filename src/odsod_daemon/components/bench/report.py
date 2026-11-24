"""Group saved results into report rows and render them (ADR-0019)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from odsod_daemon.components.bench import cases, score
from odsod_daemon.components.bench.contract import (
    BenchCase,
    BenchResult,
    Live,
    ReportRow,
)
from odsod_daemon.lib import glossary, paths


@dataclass(frozen=True)
class Group:
    measure: Literal["wer", "glossary", "latency"]
    name: str
    kind: str
    channel: str | None
    language: str | None
    unit: Literal["%", "ms"]
    target: float | None
    criterion: str

    def accepts(self, case: BenchCase) -> bool:
        return (
            case.kind == self.kind
            and (self.channel is None or case.channel == self.channel)
            and (self.language is None or case.language == self.language)
        )


GROUPS = (
    Group(
        "wer",
        "ambient mic sv",
        "ambient",
        "mic",
        "sv",
        "%",
        15,
        "live-transcript AC-3, AC-4",
    ),
    Group(
        "wer",
        "ambient mic en",
        "ambient",
        "mic",
        "en",
        "%",
        15,
        "live-transcript AC-3, AC-4",
    ),
    Group(
        "wer",
        "ambient sys sv",
        "ambient",
        "sys",
        "sv",
        "%",
        10,
        "live-transcript AC-3, AC-4",
    ),
    Group(
        "wer",
        "ambient sys en",
        "ambient",
        "sys",
        "en",
        "%",
        10,
        "live-transcript AC-3, AC-4",
    ),
    Group("wer", "dictation en", "dictation", None, "en", "%", 5, "dictation AC-6"),
    Group(
        "glossary",
        "ambient",
        "ambient",
        None,
        None,
        "%",
        None,
        "live-transcript AC-5",
    ),
    Group(
        "glossary",
        "dictation",
        "dictation",
        None,
        None,
        "%",
        None,
        "live-transcript AC-5",
    ),
    Group(
        "latency",
        "dictation",
        "dictation",
        None,
        None,
        "ms",
        2000,
        "dictation AC-3",
    ),
)


class Report(BaseModel):
    rows: list[ReportRow] = Field(default_factory=list)


@dataclass
class Bucket:
    group: Group
    result: BenchResult
    accepted: int = 0
    draft: int = 0
    failed: int = 0
    references: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)


def glossary_terms(roots: paths.Roots) -> list[str]:
    return glossary.terms(glossary.current(roots))


def _latency(result: BenchResult, case: BenchCase, roots: paths.Roots) -> int | None:
    """Request time, or the text-ready time of the live pass for dictation."""
    if result.setup.name != "live" or case.kind != "dictation":
        return result.latency_ms
    path = cases.case_dir(roots, case.id) / "live.json"
    if not path.exists():
        return result.latency_ms
    live = Live.model_validate_json(path.read_text())
    return live.ready_ms if live.ready_ms is not None else result.latency_ms


def rows(roots: paths.Roots, *, setup: str | None = None) -> list[ReportRow]:
    """One row per measure, group and fingerprint."""
    buckets: dict[tuple[str, str, str], Bucket] = {}
    terms = glossary_terms(roots)
    for case in cases.load_cases(roots):
        accepted = cases.is_accepted(roots, case)
        reference = cases.reference(roots, case) or ""
        directory = cases.case_dir(roots, case.id) / "results"
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            result = BenchResult.model_validate_json(path.read_text())
            if setup is not None and result.setup.name != setup:
                continue
            for group in GROUPS:
                if not group.accepts(case):
                    continue
                key = (group.name, group.measure, result.setup.fingerprint)
                bucket = buckets.setdefault(key, Bucket(group, result))
                if result.outcome == "failed":
                    bucket.failed += 1
                elif accepted:
                    bucket.accepted += 1
                    bucket.references.append(reference)
                    bucket.outputs.append(result.output or "")
                    latency = _latency(result, case, roots)
                    if latency is not None:
                        bucket.latencies.append(float(latency))
                else:
                    bucket.draft += 1
    return [_row(bucket, terms) for bucket in buckets.values()]


def _row(bucket: Bucket, terms: list[str]) -> ReportRow:
    group, manifest = bucket.group, bucket.result.setup
    row = ReportRow(
        measure=group.measure,
        group=group.name,
        setup=manifest.name,
        fingerprint=manifest.fingerprint,
        accepted=bucket.accepted,
        draft=bucket.draft,
        failed=bucket.failed,
        score=None,
        unit=group.unit,
        target=group.target,
        criterion=group.criterion,
    )
    if group.measure == "wer" and bucket.accepted:
        value = score.word_error_rate(bucket.references, bucket.outputs)
        row.score = None if value is None else round(value * 100, 2)
    elif group.measure == "glossary" and bucket.accepted:
        hits, total = score.glossary_hits(bucket.references, bucket.outputs, terms)
        row.score = None if not total else round(100 * hits / total, 2)
    elif group.measure == "latency" and bucket.latencies:
        row.label = "text-ready, partial" if manifest.name == "live" else "request time"
        p50 = score.percentile(bucket.latencies, 0.5)
        p95 = score.percentile(bucket.latencies, 0.95)
        row.score = p50
        row.detail = {
            "p50": p50 if p50 is not None else 0.0,
            "p95": p95 if p95 is not None else 0.0,
        }
    return row


def sort_key(row: ReportRow) -> tuple[str, str, str, str]:
    return (row.measure, row.group, row.setup, row.fingerprint)


def render(rows: list[ReportRow]) -> str:
    lines: list[str] = []
    for row in rows:
        measured = "-" if row.score is None else f"{row.score:g}"
        target = "-" if row.target is None else f"{row.target:g}"
        line = (
            f"{row.measure} {row.group} {row.setup} {row.fingerprint} "
            f"{measured} {row.unit} target {target} "
            f"accepted {row.accepted} draft {row.draft} failed {row.failed} "
            f"{row.criterion}"
        )
        if row.detail:
            line += " p50 " + f"{row.detail.get('p50', 0.0):g}"
            line += " p95 " + f"{row.detail.get('p95', 0.0):g}"
        if row.label:
            line += f" {row.label}"
        lines.append(line)
    return "\n".join(lines)


def report(roots: paths.Roots, *, setup: str | None = None) -> Report:
    return Report(rows=sorted(rows(roots, setup=setup), key=sort_key))
