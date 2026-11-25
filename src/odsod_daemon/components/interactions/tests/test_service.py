"""Gate, failure, pending and boundary invalidation checks."""

import json
from datetime import timedelta

import pytest

from odsod_daemon.components.interactions import service
from odsod_daemon.components.interactions.batch import records
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.lib import clock, paths


@pytest.fixture
def worker(temp_root):
    now = clock.utc_now()
    (temp_root / "config/config.json").write_text(
        json.dumps(
            {
                "common": {
                    "inference": {
                        "llama_url": "http://localhost:8179/v1/chat/completions",
                        "whisper_url": "http://localhost:8178",
                    }
                }
            }
        )
    )
    worker = service.Worker(InteractionsConfig(), paths.roots())
    start = now - timedelta(hours=26)
    u = dict(
        ts=clock.iso(start),
        kind="utterance",
        id="one",
        channel="sys",
        start=clock.iso(start),
        end=clock.iso(start + timedelta(seconds=10)),
    )
    worker.view.insert("utterances/ambient", u)
    for channel in ("mic", "sys"):
        worker.view.insert(
            "coverage",
            dict(
                ts=clock.iso(now), kind="covered", channel=channel, end=clock.iso(now)
            ),
        )
    worker.view.insert(
        "text", dict(u, kind="text", input="one", outcome="ok", text="Hej")
    )
    return worker


def test_interactions_ac12_waiting(worker):
    """PRD interactions AC-12: a document held back over 24 h shows Warning;
    the fault clears once the document is made."""
    worker.view.insert(
        "utterances/dictation", dict(kind="utterance", ts=clock.iso(), id="dic")
    )
    assert not worker.step()
    assert not records(worker.roots.state / "interactions")
    health = json.loads((worker.roots.run / "health/pipeline.json").read_text())
    assert health["faults"][0]["code"] == "interactions-waiting"
    assert health["faults"][0]["fix"] is None
    worker.view.insert(
        "text", dict(kind="text", ts=clock.iso(), input="dic", outcome="empty")
    )
    assert worker.step()
    assert records(worker.roots.state / "interactions")[0]["outcome"] == "skipped"
    assert not json.loads((worker.roots.run / "health/pipeline.json").read_text())[
        "faults"
    ]


def test_needs_no_inference_host_or_mains(worker, monkeypatch):
    """Owner decision 2026-11-25: interactions call no LLM, so neither power
    nor a reachable inference host holds a document back."""
    from odsod_daemon.lib import power

    monkeypatch.setattr(power, "on_mains", lambda: False)
    assert worker.step()
    assert records(worker.roots.state / "interactions")[0]["outcome"] == "skipped"


def test_bad_document_fails_once(worker, monkeypatch):
    def bad(*args):
        raise ValueError("bad front matter\nhere")

    monkeypatch.setattr(service.batch, "process", bad)
    assert worker.step()
    result = records(worker.roots.state / "interactions")[0]
    assert result["outcome"] == "failed"
    assert result["error"] == "bad front matter here"
    assert not worker.pending()


def test_overlap_after_a_split_is_kept(worker):
    """ADR-0016: a pin splits by utterance start and drops no utterance."""
    one = worker.view.data["utterances/ambient"][0]
    start = clock.parse_iso(one["start"])
    worker.view.insert(
        "events/user", dict(ts=clock.iso(start + timedelta(seconds=5)), kind="pin")
    )
    worker.view.insert(
        "utterances/ambient",
        dict(
            ts=clock.iso(start),
            kind="utterance",
            id="two",
            channel="mic",
            start=clock.iso(start + timedelta(seconds=7)),
            end=clock.iso(start + timedelta(seconds=20)),
        ),
    )
    first = worker.pending()[0]
    assert first.inputs == ["one"]
    worker.view.insert(
        "interactions",
        dict(
            ts=clock.iso(),
            kind="interaction",
            id=first.id,
            start=clock.iso(first.start),
            end=clock.iso(first.end),
            outcome="ok",
        ),
    )
    assert [b.inputs for b in worker.pending()] == [["two"]]


def test_non_boundary_records_do_not_recompute(worker, monkeypatch):
    assert worker.pending()

    def unexpected(*args):
        raise AssertionError("non-boundary record recomputed boundaries")

    monkeypatch.setattr(service, "detect", unexpected)
    for kind in ("speaking", "participants", "note", "text"):
        source = "text" if kind == "text" else "events/signals"
        worker.view.insert(source, dict(kind=kind, ts=clock.iso()))
        assert worker.pending()


def test_done_interaction_across_retention_start_is_not_found_again(worker):
    one = worker.view.data["utterances/ambient"][0]
    start = clock.parse_iso(one["start"])
    worker.view.insert(
        "interactions",
        dict(
            ts=clock.iso(),
            kind="interaction",
            id="older-start",
            start=clock.iso(start - timedelta(minutes=5)),
            end=clock.iso(start + timedelta(seconds=10)),
            outcome="ok",
        ),
    )
    assert worker.pending() == []


def test_detection_runs_at_most_every_30_s(worker, monkeypatch):
    """Detection costs about 1 s on a full day; new coverage records mark the
    view dirty several times a second, so it must not run on every wakeup."""
    calls = []
    real = service.detect
    monkeypatch.setattr(
        service, "detect", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    moment = [1000.0]
    monkeypatch.setattr(service.clock, "monotonic", lambda: moment[0])
    for _ in range(5):
        worker.view.dirty = True
        worker.pending()
    assert len(calls) == 1
    moment[0] += service.DETECT_EVERY_S
    worker.view.dirty = True
    worker.pending()
    assert len(calls) == 2


def test_old_summary_keys_still_load():
    """Keys of the old LLM summary in an owner's config.json are ignored."""
    old = {
        "model": "default",
        "chunk_chars": 37000,
        "request_timeout_s": 600,
        "max_attempts": 3,
        "title_max_words": 8,
        "languages": ["Swedish"],
        "power_check_s": 60,
        "skip_max_lines": 2,
    }
    loaded = InteractionsConfig.model_validate(old)
    assert loaded.skip_max_lines == 2
    assert "chunk_chars" not in loaded.model_dump()
