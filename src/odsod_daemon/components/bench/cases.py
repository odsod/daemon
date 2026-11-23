"""Candidate selection and case writing (ADR-0019, ``bench cases``)."""

from __future__ import annotations

import hashlib
import io
import random
import shutil
import wave
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from odsod_daemon.components.bench import setups
from odsod_daemon.components.bench.contract import (
    BenchCase,
    BenchResult,
    CaseKind,
    Live,
    LiveAsr,
    Review,
)
from odsod_daemon.lib import audio, clock, documents, paths, streams

POSTROLL_S = 0.150
"""Dictation adds this after the release (ADR-0013)."""
DRAFT_BY = "bench"


@dataclass(frozen=True)
class Candidate:
    kind: CaseKind
    source_id: str
    start: datetime
    end: datetime
    channel: str | None
    language: str | None
    text: str | None
    raw: bool
    live: Live
    ts: str


def case_root(roots: paths.Roots) -> Path:
    return roots.state / "bench"


def case_dir(roots: paths.Roots, case_id: str) -> Path:
    return case_root(roots) / case_id


def available(roots: paths.Roots, channel: str, start: datetime, end: datetime) -> bool:
    """Every hour file of the range is on disk."""
    cursor = start
    while cursor < end:
        if not audio.hour_file(roots.state, channel, cursor).exists():
            return False
        cursor = min(end, audio.hour_end(cursor))
    return True


def _live(roots: paths.Roots, text: dict, asr: list[dict]) -> Live:
    channel = text.get("channel")
    ready_ms = None
    if channel == "dic" and text.get("ts"):
        release = clock.parse_iso(text["end"]) - timedelta(seconds=POSTROLL_S)
        ready_ms = round((clock.parse_iso(text["ts"]) - release).total_seconds() * 1000)
    return Live(
        asr=[
            LiveAsr(
                backend=record.get("backend", ""),
                setup=record.get("setup"),
                text=record.get("text"),
                ms=record.get("ms"),
            )
            for record in asr
        ],
        text=text.get("text"),
        raw=bool(text.get("raw")),
        setup=text.get("setup"),
        ms=text.get("ms"),
        ready_ms=ready_ms,
    )


def _asr_records(roots: paths.Roots, source_id: str, start: datetime) -> list[dict]:
    found: list[dict] = []
    root = roots.state / "asr"
    if not root.is_dir():
        return found
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        for record in streams.read_days(
            directory, start.date(), clock.utc_now().date()
        ):
            if record.get("input") == source_id:
                found.append({**record, "backend": directory.name})
    return found


def _text_candidates(
    roots: paths.Roots, targets: setups.CaseTargets
) -> list[Candidate]:
    now = clock.utc_now()
    start = now - timedelta(days=14)
    records = streams.read_days(roots.state / "text", start.date(), now.date())
    picked: list[Candidate] = []
    for record in records:
        if record.get("outcome") != "ok" or record.get("channel") not in {
            "mic",
            "sys",
            "dic",
        }:
            continue
        begin, end = clock.parse_iso(record["start"]), clock.parse_iso(record["end"])
        seconds = (end - begin).total_seconds()
        channel = record["channel"]
        if channel == "dic":
            kind: CaseKind = "dictation"
            source_channel = "mic"
        else:
            kind = "ambient"
            source_channel = channel
            if not targets.min_s <= seconds <= targets.max_s:
                continue
            if record.get("language") not in {"sv", "en"}:
                continue
        if not available(roots, source_channel, begin, end):
            continue
        picked.append(
            Candidate(
                kind=kind,
                source_id=record["input"],
                start=begin,
                end=end,
                channel=channel,
                language=record.get("language"),
                text=record.get("text"),
                raw=bool(record.get("raw")),
                live=_live(roots, record, _asr_records(roots, record["input"], begin)),
                ts=record["ts"],
            )
        )
    return picked


def _interaction_candidates(
    roots: paths.Roots, targets: setups.CaseTargets
) -> list[Candidate]:
    now = clock.utc_now()
    start = now - timedelta(days=14)
    records = streams.read_days(roots.state / "interactions", start.date(), now.date())
    picked: list[Candidate] = []
    for record in records:
        if record.get("outcome") != "ok":
            continue
        begin, end = clock.parse_iso(record["start"]), clock.parse_iso(record["end"])
        if (end - begin).total_seconds() > targets.max_interaction_min * 60:
            continue
        if not available(roots, "mic", begin, end):
            continue
        if not available(roots, "sys", begin, end):
            continue
        picked.append(
            Candidate(
                kind="interaction",
                source_id=record["id"],
                start=begin,
                end=end,
                channel=None,
                language=None,
                text=record.get("document"),
                raw=False,
                live=Live(),
                ts=record["ts"],
            )
        )
    return picked


def candidates(roots: paths.Roots, targets: setups.CaseTargets) -> list[Candidate]:
    return _text_candidates(roots, targets) + _interaction_candidates(roots, targets)


def _stratum(case: BenchCase) -> tuple[str, ...]:
    if case.kind == "ambient":
        return ("ambient", str(case.channel), str(case.language))
    return (case.kind,)


def _target(stratum: tuple[str, ...], targets: setups.CaseTargets) -> int:
    if stratum[0] == "ambient":
        return targets.ambient_per_language
    if stratum[0] == "dictation":
        return targets.dictation
    return targets.interactions


def pick(
    roots: paths.Roots,
    candidates: list[Candidate],
    targets: setups.CaseTargets,
    *,
    seed: int,
) -> list[Candidate]:
    """Draw up to each stratum target, at most ``max_per_hour`` per UTC hour."""
    existing = load_cases(roots)
    known = {case.source_id for case in existing}
    counts: Counter[tuple[str, ...]] = Counter(_stratum(case) for case in existing)
    hours: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for case in existing:
        hours[_stratum(case)][clock.parse_iso(case.start).strftime("%Y%m%dT%H")] += 1

    grouped: dict[tuple[str, ...], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.source_id in known:
            continue
        grouped[
            ("ambient", str(candidate.channel), str(candidate.language))
            if candidate.kind == "ambient"
            else (candidate.kind,)
        ].append(candidate)

    rng = random.Random(seed)
    picks: list[Candidate] = []
    for stratum in sorted(grouped):
        need = _target(stratum, targets) - counts[stratum]
        if need <= 0:
            continue
        pool = sorted(grouped[stratum], key=lambda item: (item.start, item.source_id))
        rng.shuffle(pool)
        pool.sort(key=lambda item: item.start)
        for candidate in pool:
            if need <= 0:
                break
            hour = candidate.start.strftime("%Y%m%dT%H")
            if hours[stratum][hour] >= targets.max_per_hour:
                continue
            hours[stratum][hour] += 1
            counts[stratum] += 1
            need -= 1
            picks.append(candidate)
    return picks


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(audio.SAMPLE_RATE)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _write_live_result(
    roots: paths.Roots, directory: Path, candidate: Candidate, created: str
) -> None:
    if candidate.kind == "interaction" or candidate.live.setup is None:
        return
    asr_setup = next((entry.setup for entry in candidate.live.asr if entry.setup), None)
    fingerprint = setups.live_fingerprint(asr_setup, candidate.live.setup)
    manifest = setups.live_manifest(
        roots, asr_setup, candidate.live.setup, cleaned=True
    )
    result = BenchResult(
        setup=manifest,
        outcome="ok" if candidate.live.text else "empty",
        output=candidate.live.text,
        latency_ms=(
            None
            if candidate.live.ms is None
            else candidate.live.ms + sum(entry.ms or 0 for entry in candidate.live.asr)
        ),
        ts=created,
    )
    documents.write_json(
        directory / "results" / f"{fingerprint}.json",
        result.model_dump(mode="json", exclude_none=True),
    )


def _reference_name(kind: CaseKind) -> str:
    return "reference.md" if kind == "interaction" else "reference.txt"


def write_case(roots: paths.Roots, candidate: Candidate) -> Path:
    """Write one self-contained case directory."""
    common = setups.host_config(roots).get("common")
    host = common.get("host", "unknown") if isinstance(common, dict) else "unknown"
    case_id = (
        f"int-{candidate.source_id}"
        if candidate.kind == "interaction"
        else candidate.source_id
    )
    created = clock.iso()
    directory = case_dir(roots, case_id)
    directory.mkdir(parents=True, exist_ok=True)

    if candidate.kind == "interaction":
        for channel, name in (("mic", "mic.wav"), ("sys", "sys.wav")):
            pcm = audio.cut(roots.state, channel, candidate.start, candidate.end)
            (directory / name).write_bytes(_wav(pcm))
    else:
        channel = "mic" if candidate.channel == "dic" else str(candidate.channel)
        pcm = audio.cut(roots.state, channel, candidate.start, candidate.end)
        (directory / "audio.wav").write_bytes(_wav(pcm))

    documents.write_json(
        directory / "live.json", candidate.live.model_dump(mode="json")
    )
    case = BenchCase(
        id=case_id,
        kind=candidate.kind,
        host=str(host),
        channel=candidate.channel,
        start=clock.iso(candidate.start),
        end=clock.iso(candidate.end),
        language=candidate.language,
        source_id=candidate.source_id,
        created=created,
        commit=setups.commit(roots),
    )
    documents.write_json(directory / "case.json", case.model_dump(mode="json"))
    if candidate.kind == "interaction":
        reference = "# Reference: decisions and next steps\n\n## Decided\n\n## Next\n"
        document = roots.state / "documents/interactions" / str(candidate.text)
        if document.exists():
            documents.write(
                directory / "document.md", document.read_text(encoding="utf-8")
            )
    else:
        reference = candidate.text or ""
    documents.write(directory / _reference_name(candidate.kind), reference)
    review = Review(state="draft", drafted_by=DRAFT_BY)
    documents.write_json(directory / "review.json", review.model_dump(mode="json"))
    _write_live_result(roots, directory, candidate, created)
    return directory


def top_up(
    roots: paths.Roots,
    targets: setups.CaseTargets,
    *,
    seed: int,
    ambient: int | None = None,
    dictation: int | None = None,
    interactions: int | None = None,
) -> list[str]:
    """Top the case set up to the targets. Return the new case IDs."""
    adjusted = targets.model_copy(
        update={
            key: value
            for key, value in (
                ("ambient_per_language", ambient),
                ("dictation", dictation),
                ("interactions", interactions),
            )
            if value is not None
        }
    )
    picks = pick(roots, candidates(roots, adjusted), adjusted, seed=seed)
    return [write_case(roots, candidate).name for candidate in picks]


def load_cases(roots: paths.Roots) -> list[BenchCase]:
    directory = case_root(roots)
    if not directory.is_dir():
        return []
    found: list[BenchCase] = []
    for path in sorted(directory.iterdir()):
        case_file = path / "case.json"
        if not path.is_dir() or not case_file.exists():
            continue
        try:
            found.append(BenchCase.model_validate_json(case_file.read_text()))
        except ValueError:
            continue
    return found


def review(roots: paths.Roots, case: BenchCase) -> Review:
    path = case_dir(roots, case.id) / "review.json"
    if not path.exists():
        return Review(state="draft")
    return Review.model_validate_json(path.read_text())


def reference_path(roots: paths.Roots, case: BenchCase) -> Path:
    return case_dir(roots, case.id) / _reference_name(case.kind)


def reference_sha256(roots: paths.Roots, case: BenchCase) -> str | None:
    path = reference_path(roots, case)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def reference(roots: paths.Roots, case: BenchCase) -> str | None:
    path = reference_path(roots, case)
    return path.read_text(encoding="utf-8") if path.exists() else None


def is_accepted(roots: paths.Roots, case: BenchCase) -> bool:
    stored = review(roots, case)
    return (
        stored.state == "accepted"
        and stored.reference_sha256 is not None
        and stored.reference_sha256 == reference_sha256(roots, case)
    )


def delete(roots: paths.Roots, case_ids: list[str]) -> list[str]:
    known = {case.id for case in load_cases(roots)}
    missing = [case_id for case_id in case_ids if case_id not in known]
    if missing:
        raise KeyError(f"unknown case: {', '.join(missing)}")
    for case_id in case_ids:
        shutil.rmtree(case_dir(roots, case_id))
    return case_ids


def accept(
    roots: paths.Roots,
    case_ids: list[str],
    *,
    by: str,
    draft_by: str | None = None,
) -> list[Review]:
    known = {case.id: case for case in load_cases(roots)}
    missing = [case_id for case_id in case_ids if case_id not in known]
    if missing:
        raise KeyError(f"unknown case: {', '.join(missing)}")
    written: list[Review] = []
    for case_id in case_ids:
        case = known[case_id]
        stored = review(roots, case)
        if draft_by is not None:
            stored = stored.model_copy(update={"drafted_by": draft_by})
        else:
            stored = stored.model_copy(
                update={
                    "state": "accepted",
                    "accepted_by": by,
                    "accepted_at": clock.iso(),
                    "reference_sha256": reference_sha256(roots, case),
                }
            )
        documents.write_json(
            case_dir(roots, case_id) / "review.json",
            stored.model_dump(mode="json"),
        )
        written.append(stored)
    return written
