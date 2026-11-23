import json
import os
import subprocess
import wave
from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner

from odsod_daemon.components.bench import cases, sandbox, setups
from odsod_daemon.components.bench.cli import app
from odsod_daemon.components.bench.contract import Live
from odsod_daemon.components.bench.tests.conftest import (
    add_asr,
    add_interaction,
    add_text,
    add_utterance,
    config,
    write_audio,
)
from odsod_daemon.lib import audio, clock, paths

BENCH = {
    "cases": {
        "ambient_per_language": 2,
        "dictation": 2,
        "interactions": 1,
        "min_s": 2,
        "max_s": 30,
        "max_per_hour": 1,
        "seed": 7,
    }
}


def case_source(
    root: Path,
    *,
    channel: str = "mic",
    language: str = "sv",
    hours_ago: int = 1,
    name: str = "sv-udhr-article1",
    text: str = "Ett test om Ångström.",
):
    base = audio.hour_start(clock.utc_now()) - timedelta(hours=hours_ago)
    source = "mic" if channel == "dic" else channel
    start, end = write_audio(root, source, name, start=base)
    ident = f"{channel}-{clock.iso(start)}-{name}"
    record = add_utterance(root, ident=ident, channel=channel, start=start, end=end)
    add_text(root, record, text=text, language=language)
    add_asr(root, record)
    return start, end


def make_targets(**overrides) -> setups.CaseTargets:
    return setups.CaseTargets.model_validate({**BENCH["cases"], **overrides})


def test_cases_fill_each_stratum_at_most_per_hour(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    for hour in (2, 3, 4):
        case_source(bench_root, channel="mic", hours_ago=hour)
        case_source(
            bench_root,
            channel="mic",
            hours_ago=hour,
            name="en-chinese-feet",
            language="en",
        )
    for hour in (2, 3):
        case_source(bench_root, channel="dic", hours_ago=hour, language="en")
    case_source(bench_root, channel="sys", hours_ago=2)
    start = clock.utc_now() - timedelta(hours=2)
    add_interaction(bench_root, start, start + timedelta(seconds=30))

    written = cases.top_up(roots, make_targets(), seed=7)
    stored = cases.load_cases(roots)
    assert len(written) == len(stored)
    keys = [(case.kind, case.channel, case.language) for case in stored]
    assert keys.count(("ambient", "mic", "sv")) == 2
    assert keys.count(("ambient", "mic", "en")) == 2
    assert keys.count(("dictation", "dic", "en")) == 2
    assert keys.count(("interaction", None, None)) == 1
    per_stratum: dict[tuple, list[str]] = {}
    for case in stored:
        key = (case.kind, case.channel, case.language)
        per_stratum.setdefault(key, []).append(
            clock.parse_iso(case.start).strftime("%Y%m%dT%H")
        )
    for hours in per_stratum.values():
        assert all(hours.count(hour) <= 1 for hour in set(hours))
    # A second run has nothing left to add.
    assert cases.top_up(roots, make_targets(), seed=7) == []


def test_case_directory_holds_everything(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    start, end = case_source(bench_root)
    (bench_root / "config/glossary.txt").write_text("Ångström\n")
    case_id = cases.top_up(roots, make_targets(), seed=7)[0]
    directory = cases.case_dir(roots, case_id)

    stored = json.loads((directory / "case.json").read_text())
    assert stored["id"] == case_id == f"mic-{clock.iso(start)}-sv-udhr-article1"
    assert stored["kind"] == "ambient" and stored["channel"] == "mic"
    assert stored["language"] == "sv" and stored["host"] == "test-host"
    assert stored["source_id"] == case_id
    assert (directory / "live.json").exists()
    assert (directory / "review.json").exists()
    assert (directory / "reference.txt").read_text() == "Ett test om Ångström."
    with wave.open(str(directory / "audio.wav")) as handle:
        assert handle.getframerate() == 16000 and handle.getnchannels() == 1
        assert handle.getnframes() == round((end - start).total_seconds() * 16000)
    review = json.loads((directory / "review.json").read_text())
    assert review["state"] == "draft" and review["drafted_by"] == "bench"

    live = json.loads((directory / "live.json").read_text())
    assert live["text"] == "Ett test om Ångström."
    assert live["asr"][0]["backend"] == "whisper"
    results = list((directory / "results").glob("live-*.json"))
    assert len(results) == 1
    result = json.loads(results[0].read_text())
    assert result["setup"]["name"] == "live"


def test_interaction_case_writes_both_channels(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    start = clock.utc_now() - timedelta(hours=2)
    write_audio(bench_root, "mic", start=start)
    write_audio(bench_root, "sys", start=start)
    add_interaction(bench_root, start, start + timedelta(seconds=20), ident="abc")
    written = cases.top_up(roots, make_targets(), seed=7)
    assert written == ["int-abc"]
    directory = cases.case_dir(roots, "int-abc")
    assert (directory / "mic.wav").exists() and (directory / "sys.wav").exists()
    assert (directory / "document.md").read_text() == "# Meeting\n"
    reference = (directory / "reference.md").read_text()
    assert "## Decided" in reference and "## Next" in reference


def test_list_accept_and_hash_mismatch(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    case_source(bench_root)
    case_id = cases.top_up(roots, make_targets(), seed=7)[0]
    runner = CliRunner()

    listed = runner.invoke(app, ["list", "--json"])
    assert listed.exit_code == 0, listed.output
    document = json.loads(listed.output)
    assert document["cases"][0]["id"] == case_id
    assert document["cases"][0]["state"] == "draft"
    assert document["cases"][0]["length_s"] > 2

    drafted = runner.invoke(app, ["accept", case_id, "--draft-by", "agent"])
    assert drafted.exit_code == 0, drafted.output
    assert cases.review(roots, cases.load_cases(roots)[0]).state == "draft"

    accepted = runner.invoke(app, ["accept", case_id, "--by", "owner"])
    assert accepted.exit_code == 0, accepted.output
    review = cases.review(roots, cases.load_cases(roots)[0])
    assert review.state == "accepted" and review.accepted_by == "owner"
    assert review.reference_sha256 == cases.reference_sha256(
        roots, cases.load_cases(roots)[0]
    )

    (cases.case_dir(roots, case_id) / "reference.txt").write_text("Ny text.\n")
    assert not cases.is_accepted(roots, cases.load_cases(roots)[0])

    filtered = runner.invoke(app, ["list", "--state", "accepted"])
    assert filtered.output.strip() == ""


def test_delete_removes_the_case(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    case_source(bench_root)
    case_id = cases.top_up(roots, make_targets(), seed=7)[0]
    runner = CliRunner()
    assert runner.invoke(app, ["delete", "nope"]).exit_code == 1
    deleted = runner.invoke(app, ["delete", case_id])
    assert deleted.exit_code == 0, deleted.output
    assert not cases.case_dir(roots, case_id).exists()
    assert cases.load_cases(roots) == []


def test_retention_keeps_case_audio(bench_root):
    config(bench_root, {"bench": BENCH})
    roots = paths.roots()
    base = audio.hour_start(clock.utc_now()) - timedelta(days=30)
    start, end = write_audio(bench_root, "mic", start=base)
    candidate = cases.Candidate(
        kind="ambient",
        source_id=f"mic-{clock.iso(start)}",
        start=start,
        end=end,
        channel="mic",
        language="sv",
        text="Gammalt.",
        raw=False,
        live=Live(),
        ts=clock.iso(),
    )
    directory = cases.write_case(roots, candidate)
    assert (directory / "audio.wav").exists()

    completed = subprocess.run(
        [sandbox.console_script(), "retention"],
        env={**os.environ},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert not audio.hour_file(bench_root / "state", "mic", start).exists()
    assert (directory / "audio.wav").exists()
