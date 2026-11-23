import json
import shutil
from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner

from odsod_daemon.components.bench import cases, report, setups
from odsod_daemon.components.bench.cli import app
from odsod_daemon.components.bench.contract import (
    BenchResult,
    ModelRef,
    Outcome,
    SetupManifest,
)
from odsod_daemon.components.bench.tests.conftest import (
    add_asr,
    add_text,
    add_utterance,
    config,
    write_audio,
)
from odsod_daemon.lib import audio, clock, documents, paths

BENCH = {
    "cases": {
        "ambient_per_language": 5,
        "dictation": 5,
        "interactions": 0,
        "min_s": 2,
        "max_s": 30,
        "max_per_hour": 2,
        "seed": 3,
    }
}


def make_cases(root: Path) -> list[str]:
    base = audio.hour_start(clock.utc_now())
    for hour, channel in ((1, "mic"), (2, "mic"), (3, "dic")):
        source = "mic" if channel == "dic" else channel
        start, end = write_audio(root, source, start=base - timedelta(hours=hour))
        ident = f"{channel}-{clock.iso(start)}-{hour}"
        record = add_utterance(root, ident=ident, channel=channel, start=start, end=end)
        add_text(root, record, language="en" if channel == "dic" else "sv")
        add_asr(root, record)
    return cases.top_up(
        paths.roots(),
        setups.CaseTargets.model_validate(BENCH["cases"]),
        seed=3,
    )


def add_result(
    roots: paths.Roots,
    case,
    *,
    name: str = "large",
    fingerprint: str = "fp1",
    outcome: Outcome = "ok",
    output: str | None = None,
    latency_ms: int | None = 120,
) -> None:
    manifest = SetupManifest(
        name=name,
        kind="pipeline",
        model=ModelRef(name="ggml-large-v3"),
        commit="abc",
        fingerprint=fingerprint,
    )
    result = BenchResult(
        setup=manifest,
        outcome=outcome,
        output=output,
        latency_ms=latency_ms,
        error="boom" if outcome == "failed" else None,
        ts=clock.iso(),
    )
    documents.write_json(
        cases.case_dir(roots, case.id) / "results" / f"{fingerprint}.json",
        result.model_dump(mode="json", exclude_none=True),
    )


def setup_cases(bench_root: Path) -> tuple[paths.Roots, dict[str, str]]:
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    (bench_root / "config/glossary.txt").write_text("Ångström\n")
    written = make_cases(bench_root)
    stored = {case.kind: case for case in cases.load_cases(roots)}
    assert len(written) == 3
    for case in cases.load_cases(roots):
        shutil.rmtree(cases.case_dir(roots, case.id) / "results", ignore_errors=True)

    ambient = stored["ambient"]
    (cases.case_dir(roots, ambient.id) / "reference.txt").write_text(
        "hej på Ångström\n"
    )
    cases.accept(roots, [ambient.id], by="owner")
    add_result(roots, ambient, output="hej på Ångström")

    other = next(
        case
        for case in cases.load_cases(roots)
        if case.kind == "ambient" and case.id != ambient.id
    )
    add_result(roots, other, output="annat")

    dictation = stored["dictation"]
    cases.accept(roots, [dictation.id], by="owner")
    add_result(roots, dictation, outcome="failed", latency_ms=None)
    return roots, {"ambient": ambient.id, "other": other.id, "dict": dictation.id}


def test_rows_name_setup_count_score_and_criterion(bench_root):
    roots, _ids = setup_cases(bench_root)
    built = report.report(roots)
    assert built == report.report(roots)

    wer = [
        row
        for row in built.rows
        if row.measure == "wer" and row.group == "ambient mic sv"
    ]
    assert len(wer) == 1
    row = wer[0]
    assert row.setup == "large" and row.fingerprint == "fp1"
    assert row.accepted == 1 and row.draft == 1 and row.failed == 0
    assert row.score == 0.0 and row.target == 15 and row.unit == "%"
    assert row.criterion == "live-transcript AC-3, AC-4"

    glossary = [
        row
        for row in built.rows
        if row.measure == "glossary" and row.group == "ambient"
    ]
    assert glossary and glossary[0].score == 100.0

    failed = [
        row
        for row in built.rows
        if row.measure == "wer" and row.group == "dictation en"
    ]
    assert failed and failed[0].failed == 1 and failed[0].accepted == 0
    assert failed[0].score is None

    latency = [row for row in built.rows if row.measure == "latency"]
    assert latency and latency[0].failed == 1 and latency[0].score is None
    assert latency[0].criterion == "dictation AC-3"


def test_two_fingerprints_never_share_a_row(bench_root):
    roots, ids = setup_cases(bench_root)
    case = next(c for c in cases.load_cases(roots) if c.id == ids["ambient"])
    add_result(
        roots,
        case,
        name="large-v2",
        fingerprint="fp2",
        output="hej på Ångström",
    )
    built = report.report(roots)
    fingerprints = {
        row.fingerprint
        for row in built.rows
        if row.measure == "wer" and row.group == "ambient mic sv"
    }
    assert fingerprints == {"fp1", "fp2"}
    assert (
        len(
            [
                row
                for row in built.rows
                if row.measure == "wer" and row.group == "ambient mic sv"
            ]
        )
        == 2
    )
    filtered = report.report(roots, setup="large-v2")
    assert filtered.rows and all(row.setup == "large-v2" for row in filtered.rows)


def test_live_latency_is_text_ready(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    base = audio.hour_start(clock.utc_now())
    start, end = write_audio(bench_root, "mic", start=base - timedelta(hours=1))
    record = add_utterance(
        bench_root,
        ident=f"dic-{clock.iso(start)}",
        channel="dic",
        start=start,
        end=end,
        directory="utterances/dictation",
    )
    add_text(bench_root, record, language="en")
    add_asr(bench_root, record)
    written = cases.top_up(
        roots,
        setups.CaseTargets.model_validate(BENCH["cases"]),
        seed=3,
    )
    case = cases.load_cases(roots)[0]
    cases.accept(roots, written, by="owner")
    built = report.report(roots)
    latency = [row for row in built.rows if row.measure == "latency"]
    assert latency and latency[0].setup == "live"
    assert latency[0].label == "text-ready, partial"
    live = json.loads((cases.case_dir(roots, case.id) / "live.json").read_text())
    assert latency[0].score == live["ready_ms"]
    assert latency[0].detail["p95"] == live["ready_ms"]


def test_report_json_holds_every_text_field(bench_root):
    setup_cases(bench_root)
    runner = CliRunner()
    result = runner.invoke(app, ["report", "--json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["rows"]
    for row in document["rows"]:
        for key in (
            "measure",
            "group",
            "setup",
            "fingerprint",
            "criterion",
            "label",
            "unit",
        ):
            assert key in row
    text = runner.invoke(app, ["report"])
    assert text.exit_code == 0
    assert "live-transcript AC-3, AC-4" in text.output
