"""Build a sandbox root, run speech ``--once`` and read the records back."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from odsod_daemon.components.bench import setups
from odsod_daemon.components.bench.contract import (
    BenchCase,
    Outcome,
    SetupManifest,
)
from odsod_daemon.lib import audio, clock, documents, paths, streams

GAP_S = 5
"""Synthetic seconds between two cases (ADR-0019)."""
COMMAND_TIMEOUT_S = 900
PROMPTS = {"ambient": "cleanup", "dictation": "cleanup-dictation"}


@dataclass(frozen=True)
class RunResult:
    case: BenchCase
    outcome: Outcome
    output: str | None = None
    latency_ms: int | None = None
    error: str | None = None


def console_script() -> str:
    """The ``odsodctl`` next to this interpreter, or one on ``PATH``."""
    candidate = Path(sys.executable).with_name("odsodctl")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("odsodctl")
    if found is None:
        raise RuntimeError("odsodctl not found; install the package")
    return found


def execute(
    target: str, base: Path, *, timeout_s: float = COMMAND_TIMEOUT_S
) -> str | None:
    """Run ``odsodctl run <target> --once`` in the sandbox. Error line or None."""
    env = {**os.environ, paths.OVERRIDE: str(base)}
    completed = subprocess.run(
        [console_script(), "run", target, "--once"],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if completed.returncode == 0:
        return None
    lines = [
        line.strip()
        for line in (completed.stderr or completed.stdout).splitlines()
        if line.strip()
    ]
    return lines[-1] if lines else f"{target}: exit {completed.returncode}"


def _pcm(path: Path) -> bytes:
    with wave.open(str(path)) as handle:
        return handle.readframes(handle.getnframes())


def write_pcm(state: Path, channel: str, start: datetime, pcm: bytes) -> None:
    """Write PCM into the hourly buffer at ``start``, split by hour."""
    offset = 0
    cursor = start
    while offset < len(pcm):
        hour = audio.hour_start(cursor)
        hour_offset = round((cursor - hour).total_seconds() * audio.BYTES_PER_SECOND)
        room = audio.BYTES_PER_SECOND * 3600 - hour_offset
        piece = pcm[offset : offset + room]
        path = audio.hour_file(state, channel, cursor)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+b" if path.exists() else "wb"
        with path.open(mode) as handle:
            handle.seek(hour_offset)
            handle.write(piece)
        offset += len(piece)
        cursor = cursor + timedelta(seconds=len(piece) / audio.BYTES_PER_SECOND)


def _prompt_sources(setup: setups.Setup) -> dict[str, str | None]:
    if setup.kind != "pipeline":
        return {}
    cleanup = setup.cleanup
    return {
        "ambient": None if cleanup is None else cleanup.ambient_prompt,
        "dictation": None if cleanup is None else cleanup.dictation_prompt,
    }


def _write_config(
    base: Path, roots: paths.Roots, setup: setups.Setup, settings: dict[str, object]
) -> None:
    conf = setups.host_config(roots)
    common = conf.get("common")
    if not isinstance(common, dict):
        common = {}
        conf["common"] = common
    inference = common.get("inference")
    if not isinstance(inference, dict):
        inference = {}
        common["inference"] = inference
    if setup.asr.whisper_url:
        inference["whisper_url"] = setup.asr.whisper_url
    if setup.kind == "pipeline" and setup.cleanup and setup.cleanup.llama_url:
        inference["llama_url"] = setup.cleanup.llama_url
    conf["speech"] = settings
    documents.write_json(base / "config/config.json", conf)

    glossary = roots.config / "glossary.txt"
    if glossary.exists():
        documents.write(base / "config/glossary.txt", glossary.read_bytes())

    for lane, live_name in PROMPTS.items():
        name = _prompt_sources(setup).get(lane)
        if name is None:
            source = roots.config / "prompts" / f"{live_name}.md"
        else:
            source = roots.config / "prompts" / f"{name}.md"
            if not source.exists():
                raise ValueError(f"{name}: prompt file not found")
        if source.exists():
            documents.write(
                base / "config/prompts" / f"{live_name}.md", source.read_bytes()
            )


def build(
    base: Path,
    roots: paths.Roots,
    setup: setups.Setup,
    manifest: SetupManifest,
    cases: list[BenchCase],
) -> dict[str, BenchCase]:
    """Fill a temp root. Return the synthetic ID to case map."""
    for name in ("state", "run", "config"):
        (base / name).mkdir(parents=True, exist_ok=True)
    _write_config(base, roots, setup, manifest.settings)

    mapping: dict[str, BenchCase] = {}
    cursor = audio.hour_start(clock.utc_now())
    for case in cases:
        start = cursor
        end = start + (clock.parse_iso(case.end) - clock.parse_iso(case.start))
        directory = roots.state / "bench" / case.id
        dic = case.kind == "dictation"
        channel = "mic" if dic else str(case.channel)
        write_pcm(base / "state", channel, start, _pcm(directory / "audio.wav"))
        synthetic = f"{case.kind}-{clock.iso(start)}"
        record = {
            "ts": clock.iso(end),
            "kind": "utterance",
            "id": synthetic,
            "channel": "dic" if dic else channel,
            "start": clock.iso(start),
            "end": clock.iso(end),
        }
        directory_name = "dictation" if dic else "ambient"
        streams.append(
            streams.day_path(base / "state/utterances" / directory_name, start.date()),
            record,
        )
        mapping[synthetic] = case
        cursor = end + timedelta(seconds=GAP_S)
    return mapping


def _records(root: Path, directory: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for record in streams.read_day(path):
            if "input" in record:
                found[record["input"]] = record
    return found


def _outcome(record: dict | None, error: str | None) -> tuple[Outcome, str | None]:
    if record is None:
        return "failed", error or "no record"
    value = record.get("outcome")
    if value == "ok":
        return "ok", None
    if value == "empty":
        return "empty", None
    if value == "expired":
        return "failed", "expired"
    return "failed", record.get("error") or error or "failed"


def read_back(
    base: Path,
    mapping: dict[str, BenchCase],
    setup: setups.Setup,
    error: str | None,
) -> list[RunResult]:
    asr: dict[str, dict] = {}
    root = base / "state/asr"
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            if directory.is_dir():
                asr.update(_records(base, directory))
    text = _records(base, base / "state/text")

    results: list[RunResult] = []
    for synthetic, case in mapping.items():
        asr_record = asr.get(synthetic)
        if setup.kind == "asr":
            outcome, why = _outcome(asr_record, error)
            results.append(
                RunResult(
                    case=case,
                    outcome=outcome,
                    output=None if asr_record is None else asr_record.get("text"),
                    latency_ms=None if asr_record is None else asr_record.get("ms"),
                    error=why,
                )
            )
            continue
        text_record = text.get(synthetic)
        outcome, why = _outcome(text_record, error)
        latency = None
        if asr_record is not None and text_record is not None:
            latency = (asr_record.get("ms") or 0) + (text_record.get("ms") or 0)
        results.append(
            RunResult(
                case=case,
                outcome=outcome,
                output=None if text_record is None else text_record.get("text"),
                latency_ms=latency,
                error=why,
            )
        )
    return results


def run(
    setup: setups.Setup,
    manifest: SetupManifest,
    roots: paths.Roots,
    cases: list[BenchCase],
    *,
    isolated: bool = False,
) -> list[RunResult]:
    """Run the setup over the cases in one sandbox, or one per case."""
    groups = [[case] for case in cases] if isolated else [cases]
    results: list[RunResult] = []
    for group in groups:
        if not group:
            continue
        base = Path(tempfile.mkdtemp(prefix="odsod-bench-"))
        try:
            mapping = build(base, roots, setup, manifest, group)
            error = execute("transcription", base)
            if error is None and setup.kind == "pipeline":
                error = execute("cleanup", base)
            results.extend(read_back(base, mapping, setup, error))
        finally:
            shutil.rmtree(base, ignore_errors=True)
    return results
