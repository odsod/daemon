import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.bench import adapters, cases, runner, sandbox, setups
from odsod_daemon.components.bench.contract import Live
from odsod_daemon.components.bench.tests.conftest import (
    add_asr,
    add_text,
    add_utterance,
    config,
    write_audio,
)
from odsod_daemon.lib import audio, clock, inference, paths

DATA = Path(inference.__file__).parent / "testdata"
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


def snapshot(root: Path) -> list[str]:
    return sorted(str(path) for path in root.rglob("*") if "results" not in path.parts)


def pair(name: str, *, delay_ms: int = 0) -> dict:
    value = json.loads((DATA / f"{name}.json").read_text())
    value["response"]["delay_ms"] = delay_ms
    return value


def configure(root: Path, whisper: str, llama: str) -> None:
    value = config(root, {"bench": BENCH})
    value["common"]["inference"] = {"whisper_url": whisper, "llama_url": llama}
    (root / "config/config.json").write_text(json.dumps(value))


def setup(kind: str = "pipeline", **cleanup) -> setups.Setup:
    return setups.Setup.model_validate(
        {
            "name": "fake",
            "kind": kind,
            "asr": {"model": "ggml-large-v3-turbo"},
            "cleanup": {"model": "qwen3", **cleanup} if kind == "pipeline" else None,
        }
    )


def two_ambient_cases(root: Path) -> list[str]:
    base = audio.hour_start(clock.utc_now())
    for hour in (1, 2):
        start, end = write_audio(root, "mic", start=base - timedelta(hours=hour))
        ident = f"mic-{clock.iso(start)}-{hour}"
        record = add_utterance(root, ident=ident, channel="mic", start=start, end=end)
        add_text(root, record)
        add_asr(root, record)
    return cases.top_up(
        paths.roots(),
        setups.CaseTargets.model_validate(BENCH["cases"]),
        seed=3,
    )


def servers(count: int):
    whisper = inference.ReplayServer([pair("whisper-sv-verbose") for _ in range(count)])
    llama = inference.ReplayServer(
        [pair("llama-cleanup-ambient") for _ in range(count)]
    )
    return whisper, llama


@pytest.mark.looptime(False)
def test_quality_run_reads_one_record_per_case(bench_root, monkeypatch):
    whisper, llama = servers(2)
    try:
        configure(
            bench_root,
            whisper.url + inference.WHISPER_PATH,
            llama.url + inference.LLAMA_PATH,
        )
        written = two_ambient_cases(bench_root)
        assert len(written) == 2
        before = snapshot(bench_root)

        calls: list[str] = []
        original = sandbox.execute

        def counting(target: str, base: Path, **kwargs):
            calls.append(target)
            return original(target, base, **kwargs)

        monkeypatch.setattr(sandbox, "execute", counting)
        summary = runner.run(paths.roots(), setup())
        assert calls == ["transcription", "cleanup"]
        assert summary.ran == 2 and summary.ok == 2 and summary.failed == 0
        stored = cases.load_cases(paths.roots())
        for case in stored:
            result = runner.result(paths.roots(), case, summary.fingerprint)
            assert result is not None and result.outcome == "ok"
            assert result.output and "människor" in result.output
            assert result.latency_ms is not None
        assert snapshot(bench_root) == before
    finally:
        whisper.close()
        llama.close()


@pytest.mark.looptime(False)
def test_old_case_runs_at_a_synthetic_time(bench_root):
    whisper, llama = servers(1)
    try:
        configure(
            bench_root,
            whisper.url + inference.WHISPER_PATH,
            llama.url + inference.LLAMA_PATH,
        )
        start = audio.hour_start(clock.utc_now()) - timedelta(days=180)
        begin, end = write_audio(bench_root, "mic", start=start)
        candidate = cases.Candidate(
            kind="ambient",
            source_id=f"mic-{clock.iso(begin)}",
            start=begin,
            end=end,
            channel="mic",
            language="sv",
            text="Gammalt.",
            raw=False,
            live=Live(),
            ts=clock.iso(),
        )
        directory = cases.write_case(paths.roots(), candidate)
        summary = runner.run(paths.roots(), setup("asr"))
        result = runner.result(
            paths.roots(), cases.load_cases(paths.roots())[0], summary.fingerprint
        )
        assert summary.ok == 1 and result is not None
        assert result.outcome == "ok" and result.output
        assert list((directory / "results").glob("*.json"))
    finally:
        whisper.close()
        llama.close()


def test_prompts_land_in_the_sandbox(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    (bench_root / "config/prompts").mkdir()
    (bench_root / "config/prompts/terse.md").write_text("AMBIENT PROMPT\n")
    (bench_root / "config/prompts/short.md").write_text("DICTATION PROMPT\n")
    seen: dict[str, str] = {}

    def capture(target: str, base: Path, **kwargs):
        for path in (base / "config/prompts").glob("*.md"):
            seen[path.name] = path.read_text()
        conf = json.loads((base / "config/config.json").read_text())
        assert conf["speech"]["attempts"] == 1
        return "stop"

    monkeypatch.setattr(sandbox, "execute", capture)
    summary = runner.run(
        paths.roots(),
        setups.Setup.model_validate(
            {
                "name": "prompted",
                "kind": "pipeline",
                "asr": {"model": "m", "settings": {"attempts": 1}},
                "cleanup": {"model": "c", "ambient_prompt": "terse"},
            }
        ),
    )
    assert seen == {"cleanup.md": "AMBIENT PROMPT\n"}
    assert summary.failed == summary.ran


@pytest.mark.looptime(False)
def test_nonzero_once_command_fails_the_case(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    monkeypatch.setattr(
        sandbox,
        "execute",
        lambda target, base, **kwargs: (
            "whisper: host unavailable; work remains pending"
        ),
    )
    summary = runner.run(paths.roots(), setup("asr"))
    assert summary.failed == 2
    stored = runner.result(
        paths.roots(), cases.load_cases(paths.roots())[0], summary.fingerprint
    )
    assert stored is not None and stored.outcome == "failed"
    assert stored.error == "whisper: host unavailable; work remains pending"


def test_isolated_run_pays_the_start_per_case(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    calls: list[tuple[str, str]] = []

    def capture(target: str, base: Path, **kwargs):
        calls.append((target, str(base)))
        return "stop"

    monkeypatch.setattr(sandbox, "execute", capture)
    runner.run(paths.roots(), setup("asr"), isolated=True)
    assert [target for target, _ in calls] == ["transcription", "transcription"]
    assert calls[0][1] != calls[1][1]


def test_resume_skips_finished_cases(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    monkeypatch.setattr(sandbox, "execute", lambda target, base, **kwargs: "boom")
    first = runner.run(paths.roots(), setup("asr"))
    assert first.ran == 2
    second = runner.run(paths.roots(), setup("asr"))
    assert second.ran == 0
    retried = runner.run(paths.roots(), setup("asr"), retry_failed=True)
    assert retried.ran == 2


def test_sandbox_adapter_kinds_and_cloud_rule(bench_root):
    manifest = setups.manifest(setup(), paths.roots())
    local = adapters.SandboxAdapter(setup(), manifest, paths.roots())
    assert local.accepts("ambient") and local.accepts("dictation")
    assert not local.accepts("interaction")
    adapters.check_contract(local)

    class CloudLike(adapters.SandboxAdapter):
        def accepts(self, kind: str) -> bool:
            return True

    with pytest.raises(ValueError, match="dictation cases only"):
        adapters.check_contract(CloudLike(setup(), manifest, paths.roots()), cloud=True)


def test_synthetic_times_stay_in_the_past_near_midnight(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    stored = cases.load_cases(paths.roots())
    now = datetime(2026, 11, 23, 23, 0, 1, tzinfo=UTC)
    monkeypatch.setattr(clock, "utc_now", lambda: now)
    chosen = setup("asr")
    manifest = setups.manifest(chosen, paths.roots())
    base = bench_root / "sandbox"
    mapping = sandbox.build(base, paths.roots(), chosen, manifest, stored)
    assert len(mapping) == 2
    days = [path.stem for path in (base / "state/utterances/ambient").glob("*.jsonl")]
    assert days and all(day <= "2026-11-23" for day in days)
    for path in (base / "state/utterances/ambient").glob("*.jsonl"):
        for line in path.read_text().splitlines():
            assert clock.parse_iso(json.loads(line)["end"]) <= now


def test_setup_cases_limit_the_adapter(bench_root):
    chosen = setups.Setup.model_validate(
        {
            "name": "dictation-only",
            "kind": "asr",
            "cases": ["dictation"],
            "asr": {"model": "m"},
        }
    )
    manifest = setups.manifest(chosen, paths.roots())
    adapter = adapters.SandboxAdapter(chosen, manifest, paths.roots())
    assert adapter.accepts("dictation")
    assert not adapter.accepts("ambient")


def test_interrupted_isolated_run_keeps_finished_results(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    calls: list[str] = []

    def stop_on_second(target: str, base: Path, **kwargs):
        calls.append(target)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return "boom"

    monkeypatch.setattr(sandbox, "execute", stop_on_second)
    with pytest.raises(KeyboardInterrupt):
        runner.run(paths.roots(), setup("asr"), isolated=True)
    fingerprint = setups.manifest(setup("asr"), paths.roots()).fingerprint
    stored = [
        runner.result(paths.roots(), case, fingerprint)
        for case in cases.load_cases(paths.roots())
    ]
    assert sum(1 for item in stored if item is not None) == 1
    monkeypatch.setattr(sandbox, "execute", lambda target, base, **kwargs: "boom")
    assert runner.run(paths.roots(), setup("asr"), isolated=True).ran == 1


def test_pipeline_cleans_what_transcription_finished(bench_root, monkeypatch):
    configure(
        bench_root,
        "http://127.0.0.1:1/v1/audio/transcriptions",
        "http://127.0.0.1:1/v1/chat/completions",
    )
    two_ambient_cases(bench_root)
    calls: list[str] = []

    def utterances(base: Path) -> list[dict]:
        return [
            json.loads(line)
            for path in sorted((base / "state/utterances/ambient").glob("*.jsonl"))
            for line in path.read_text().splitlines()
        ]

    def partial(target: str, base: Path, **kwargs):
        calls.append(target)
        first = utterances(base)[0]
        if target == "transcription":
            add_asr(base, first)
            return "whisper: host unavailable; work remains pending"
        add_text(base, first, text="Rent.")
        return None

    monkeypatch.setattr(sandbox, "execute", partial)
    summary = runner.run(paths.roots(), setup())
    assert calls == ["transcription", "cleanup"]
    assert summary.ok == 1 and summary.failed == 1
    stored = [
        runner.result(paths.roots(), case, summary.fingerprint)
        for case in cases.load_cases(paths.roots())
    ]
    outcomes = sorted(
        (item.outcome, item.output, item.error) for item in stored if item is not None
    )
    assert outcomes == [
        ("failed", None, "whisper: host unavailable; work remains pending"),
        ("ok", "Rent.", None),
    ]
