"""Power, retry, pending and boundary invalidation checks."""

import json
from datetime import timedelta

import pytest

from odsod_daemon.components.interactions import service
from odsod_daemon.components.interactions.batch import records
from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.summarize import Summary
from odsod_daemon.lib import clock, paths, power

REAL_ON_MAINS = power.on_mains


@pytest.fixture
def worker(temp_root, monkeypatch):
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

    async def reachable(*args):
        return True

    monkeypatch.setattr(service.inference, "reachable", reachable)

    async def summarize(self, text):
        return Summary(
            skip=False, title="Title", overview="Overview.", points=[]
        ), "fake"

    monkeypatch.setattr(service.Summarizer, "__call__", summarize)
    monkeypatch.setattr(service.power, "on_mains", lambda: True)
    return worker


async def test_power_and_waiting(worker, temp_root, monkeypatch):
    supply = temp_root / "power/BAT0"
    supply.mkdir(parents=True)
    (supply / "type").write_text("Battery")
    (supply / "status").write_text("Discharging")
    monkeypatch.setattr(
        service.power, "on_mains", lambda: REAL_ON_MAINS(temp_root / "power")
    )
    assert not await worker.step()
    assert not records(worker.roots.state / "interactions")
    health = json.loads((worker.roots.run / "health/pipeline.json").read_text())
    assert health["faults"][0]["code"] == "interactions-waiting"
    assert health["faults"][0]["fix"] is None
    (supply / "status").write_text("Charging")
    await clock.sleep(60)
    assert await worker.step()
    assert not json.loads((worker.roots.run / "health/pipeline.json").read_text())[
        "faults"
    ]


async def test_pending_gate_and_host_returns(worker, monkeypatch):
    worker.view.insert(
        "utterances/dictation", dict(kind="utterance", ts=clock.iso(), id="dic")
    )
    assert not await worker.step()
    worker.view.insert(
        "text", dict(kind="text", ts=clock.iso(), input="dic", outcome="empty")
    )

    async def down(*args):
        return False

    monkeypatch.setattr(service.inference, "reachable", down)
    assert not await worker.step()
    assert not worker.attempts

    async def up(*args):
        return True

    monkeypatch.setattr(service.inference, "reachable", up)
    await clock.sleep(60)
    assert await worker.step()


async def test_retries_and_failure(worker, monkeypatch):
    calls = []

    async def bad(self, text):
        calls.append(clock.monotonic())
        raise ValueError("invalid JSON\nreply")

    monkeypatch.setattr(service.Summarizer, "__call__", bad)
    assert not await worker.step()
    assert not await worker.step()
    await clock.sleep(60)
    assert not await worker.step()
    await clock.sleep(300)
    assert await worker.step()
    result = records(worker.roots.state / "interactions")[0]
    assert result["outcome"] == "failed"
    assert result["error"] == "invalid JSON reply"
    assert len(calls) == 3
    assert not list((worker.roots.state / "documents/interactions").glob("*.md"))


def test_non_boundary_records_do_not_recompute(worker, monkeypatch):
    assert worker.pending()

    def unexpected(*args):
        raise AssertionError("non-boundary record recomputed boundaries")

    monkeypatch.setattr(service, "detect", unexpected)
    for kind in ("speaking", "participants", "note", "text"):
        source = "text" if kind == "text" else "events/signals"
        worker.view.insert(source, dict(kind=kind, ts=clock.iso()))
        assert worker.pending()
