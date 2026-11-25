"""The capture service loop on the virtual clock and a fake pw-record."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from odsod_daemon.components.capture import channel, service
from odsod_daemon.components.capture.config import CaptureConfig
from odsod_daemon.components.capture.tests.helpers import (
    WALL_BASE,
    FakePwRecord,
    FakeSource,
    feed_blocks,
    health_faults,
    records_of,
)
from odsod_daemon.lib import audio, clock, documents, systemd


def config(**overrides: float) -> CaptureConfig:
    values: dict[str, float] = {
        "stall_restart_s": 0.3,
        "stall_error_s": 1.0,
        "mic_silent_s": 0.5,
        "reanchor_ms": 150.0,
        "capture_latency_ms": 0.0,
    }
    values.update(overrides)
    return CaptureConfig(**values)


async def run_capture(
    root: Path,
    *,
    seconds: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    settings: CaptureConfig | None = None,
) -> None:
    stopping = asyncio.Event()

    async def stop() -> None:
        await clock.sleep(seconds)
        stopping.set()

    stopper = asyncio.create_task(stop())
    await service.run(
        settings or config(),
        state_root=root / "state",
        run_root=root / "run",
        spawner=fake_pw,
        watcher=fake_source,
        stopping=stopping,
    )
    await stopper


def coverage(root: Path, channel: str, starts: list[dict]) -> float:
    covered = audio.covered_until(root / "state", channel)
    assert covered is not None
    return covered.timestamp() - WALL_BASE - _seconds(starts[0]["audio_start"])


def _seconds(text: str) -> float:
    return clock.parse_iso(text).timestamp() - WALL_BASE


async def test_start_writes_audio_and_sigterm_writes_stop(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
) -> None:
    for name in ("mic", "sys"):
        fake_pw.script(name, feed_blocks(30))  # type: ignore[arg-type]
    await run_capture(tmp_path, seconds=1.0, fake_pw=fake_pw, fake_source=fake_source)
    for name in ("mic", "sys"):
        starts = records_of(tmp_path, "start", name)
        stops = records_of(tmp_path, "stop", name)
        assert len(starts) == 1
        assert len(stops) == 1
        assert starts[0]["prev_end"] is None
        assert stops[0]["reason"] == "shutdown"
        assert coverage(tmp_path, name, starts) == pytest.approx(1.0, abs=0.01)
    assert records_of(tmp_path, "gap") == []
    assert health_faults(tmp_path) == []


async def test_stall_restarts_pw_record_and_writes_a_gap(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
) -> None:
    fake_pw.script("mic", feed_blocks(5), feed_blocks(10))
    fake_pw.script("sys", feed_blocks(30))
    await run_capture(
        tmp_path,
        seconds=2.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=1.2),
    )
    assert fake_pw.spawns.count("mic") == 2
    starts = records_of(tmp_path, "start", "mic")
    assert len(starts) == 1
    first_end = _seconds(starts[0]["audio_start"]) + 0.5
    gaps = records_of(tmp_path, "gap", "mic")
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "stall"
    assert _seconds(gaps[0]["start"]) == pytest.approx(first_end)
    assert _seconds(gaps[0]["end"]) - first_end >= 1.0


async def test_capture_stalled_after_sixty_seconds_without_audio(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
) -> None:
    fake_pw.script("sys", feed_blocks(50))
    settings = config(stall_error_s=1.0, stall_restart_s=5.0)
    await run_capture(
        tmp_path,
        seconds=1.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=settings,
    )
    faults = health_faults(tmp_path)
    assert [(fault["code"], fault["key"]) for fault in faults] == [
        ("capture-stalled", "mic")
    ]
    assert _seconds(faults[0]["since"]) == pytest.approx(0.0, abs=0.2)


async def test_capture_stalled_starts_at_the_newest_audio(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
) -> None:
    fake_pw.script("mic", feed_blocks(5))
    fake_pw.script("sys", feed_blocks(50))
    settings = config(stall_error_s=0.5, stall_restart_s=5.0)
    await run_capture(
        tmp_path,
        seconds=1.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=settings,
    )
    faults = health_faults(tmp_path)
    assert faults[0]["code"] == "capture-stalled"
    assert _seconds(faults[0]["since"]) == pytest.approx(0.4, abs=0.05)


async def test_mic_silent_appears_and_one_sample_clears_it(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
) -> None:
    fake_pw.script("mic", feed_blocks(12, value=0))
    fake_pw.script("sys", feed_blocks(50))
    await run_capture(tmp_path, seconds=1.2, fake_pw=fake_pw, fake_source=fake_source)
    faults = health_faults(tmp_path)
    assert [(fault["code"], fault["key"]) for fault in faults] == [("mic-silent", None)]
    assert _seconds(faults[0]["since"]) == pytest.approx(-0.1, abs=0.05)

    cleared = FakePwRecord()
    cleared.script("mic", feed_blocks(11, value=0), feed_blocks(10, delay=0.1))
    cleared.script("sys", feed_blocks(50))
    await run_capture(tmp_path, seconds=2.5, fake_pw=cleared, fake_source=fake_source)
    assert [fault["code"] for fault in health_faults(tmp_path)] == []


async def test_muted_source_shows_mic_muted_and_no_silent_fault(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
) -> None:
    muted = FakeSource(muted=True)
    fake_pw.script("mic", feed_blocks(20, value=0))
    fake_pw.script("sys", feed_blocks(50))
    await run_capture(tmp_path, seconds=1.2, fake_pw=fake_pw, fake_source=muted)
    assert [fault["code"] for fault in health_faults(tmp_path)] == ["mic-muted"]


async def test_watchdog_pings_stop_when_a_channel_goes_quiet(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pings: list[float] = []
    monkeypatch.setattr(
        systemd,
        "sd_notify",
        lambda state: pings.append(clock.wall()) or True,
    )
    for name in ("mic", "sys"):
        fake_pw.script(name, feed_blocks(20))  # type: ignore[arg-type]
    await run_capture(
        tmp_path,
        seconds=8.0,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=5.0, stall_error_s=60.0),
    )
    assert pings
    assert max(pings) - WALL_BASE < 7.5


async def test_restart_start_has_prev_end_from_the_file_size(
    tmp_path: Path,
    virtual_wall: float,
    fake_source: FakeSource,
) -> None:
    first = FakePwRecord()
    for name in ("mic", "sys"):
        first.script(name, feed_blocks(20))  # type: ignore[arg-type]
    await run_capture(tmp_path, seconds=1.0, fake_pw=first, fake_source=fake_source)
    covered = audio.covered_until(tmp_path / "state", "mic")
    assert covered is not None
    before = covered.timestamp()
    second = FakePwRecord()
    for name in ("mic", "sys"):
        second.script(name, feed_blocks(20))  # type: ignore[arg-type]
    await run_capture(tmp_path, seconds=1.0, fake_pw=second, fake_source=fake_source)
    starts = records_of(tmp_path, "start", "mic")
    assert len(starts) == 2
    assert starts[1]["prev_end"] is not None
    assert _seconds(starts[1]["prev_end"]) == pytest.approx(
        before - WALL_BASE, abs=0.002
    )
    assert _seconds(starts[1]["audio_start"]) >= _seconds(starts[1]["prev_end"]) - 0.002
    assert coverage(tmp_path, "mic", starts) == pytest.approx(2.0, abs=0.01)


@pytest.mark.parametrize("suspend_s", [0.0, 5.0])
async def test_suspend_restarts_and_writes_a_gap(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    monkeypatch: pytest.MonkeyPatch,
    suspend_s: float,
) -> None:
    offset = {"value": 0.0}
    monkeypatch.setattr(
        clock,
        "wall",
        lambda: (
            WALL_BASE
            + asyncio.get_running_loop().time()
            + (suspend_s if offset["value"] else 0.0)
        ),
    )
    monkeypatch.setattr(
        clock,
        "boottime",
        lambda: 1_000.0 + asyncio.get_running_loop().time() + offset["value"],
    )
    monkeypatch.setattr(
        clock, "monotonic", lambda: 1_000.0 + asyncio.get_running_loop().time()
    )
    fake_pw.script("mic", feed_blocks(1), feed_blocks(20))
    fake_pw.script("sys", feed_blocks(1), feed_blocks(20))

    async def bump() -> None:
        await clock.sleep(0.5)
        offset["value"] = 5.0

    bumper = asyncio.create_task(bump())
    await run_capture(
        tmp_path,
        seconds=1.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=2.0),
    )
    await bumper
    assert fake_pw.spawns.count("mic") == 2
    gaps = records_of(tmp_path, "gap", "mic")
    assert len(records_of(tmp_path, "start", "mic")) == 1
    if suspend_s:
        assert [gap["reason"] for gap in gaps] == ["suspend"]
        assert _seconds(gaps[0]["start"]) == pytest.approx(0.0, abs=0.05)
        assert _seconds(gaps[0]["end"]) - _seconds(gaps[0]["start"]) >= 1.0
    else:
        assert gaps == []


def test_stream_arguments_set_the_app_and_node_names() -> None:
    mic = channel.stream_arguments("mic")
    sys = channel.stream_arguments("sys")
    for args in (mic, sys):
        text = " ".join(args)
        assert "--rate 16000 --channels 1 --format s16 --raw" in text
        assert "application.name = odsod-daemon-capture" in text
        assert "node.name = odsod-daemon-capture-" in text
        assert args[-1] == "-"
    assert "stream.capture.sink = true" not in " ".join(mic)
    assert "stream.capture.sink = true" in " ".join(sys)
    assert "node.name = odsod-daemon-capture-sys" in " ".join(sys)


def test_records_use_the_seam_fields(tmp_path: Path) -> None:
    from odsod_daemon.components.capture.contract import (
        CaptureGap,
        CaptureStart,
        CaptureStop,
    )

    start = CaptureStart(ts="t", channel="mic", audio_start="a", prev_end=None)
    assert start.model_dump() == {
        "ts": "t",
        "kind": "start",
        "channel": "mic",
        "audio_start": "a",
        "prev_end": None,
    }
    stop = CaptureStop(ts="t", channel="sys")
    assert stop.model_dump()["reason"] is None
    gap = CaptureGap(
        ts="t",
        channel="mic",
        start="a",
        end="b",
        reason="stall",
    )
    assert gap.model_dump()["reason"] == "stall"


def test_health_file_holds_the_service_name(tmp_path: Path) -> None:
    from odsod_daemon.lib import healthfile

    path = tmp_path / "run" / "health" / "capture.json"
    document = healthfile.HealthFile(path, "capture").rewrite()
    assert documents.read_json(path)["service"] == "capture"
    assert document.faults == []


@pytest.mark.parametrize("eof", [False, True])
@pytest.mark.parametrize("restart_s", [0.3, 1.2])
async def test_restart_records_only_holes_of_at_least_one_second(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    eof: bool,
    restart_s: float,
) -> None:
    fake_pw.script("mic", feed_blocks(5, eof=eof), feed_blocks(10))
    fake_pw.script("sys", feed_blocks(40))
    await run_capture(
        tmp_path,
        seconds=2.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=restart_s),
    )
    assert len(records_of(tmp_path, "start", "mic")) == 1
    gaps = records_of(tmp_path, "gap", "mic")
    assert len(gaps) == (1 if restart_s >= 1.0 else 0)
    if gaps:
        assert gaps[0]["reason"] == "stall"
        assert _seconds(gaps[0]["start"]) == pytest.approx(0.4)
        assert _seconds(gaps[0]["end"]) - _seconds(gaps[0]["start"]) >= 1.0


async def test_watchdog_stops_after_a_backward_wall_clock_step(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pings: list[float] = []
    monkeypatch.setattr(clock, "monotonic", lambda: asyncio.get_running_loop().time())
    monkeypatch.setattr(clock, "boottime", lambda: clock.monotonic())
    monkeypatch.setattr(
        clock,
        "wall",
        lambda: WALL_BASE + clock.monotonic() - (100 if clock.monotonic() >= 3 else 0),
    )
    monkeypatch.setattr(
        systemd,
        "sd_notify",
        lambda state: pings.append(clock.monotonic()) or True,
    )
    for name in ("mic", "sys"):
        fake_pw.script(name, feed_blocks(20))  # type: ignore[arg-type]
    await run_capture(
        tmp_path,
        seconds=10,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=20, stall_error_s=60),
    )
    assert pings
    assert max(pings) < 7.0


async def test_resume_from_suspend_is_not_a_stall(
    tmp_path: Path,
    virtual_wall: float,
    fake_pw: FakePwRecord,
    fake_source: FakeSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lid close stops the clocks of the audio, not the wall clock. The first
    health tick after the wake must not see the pre-suspend audio as a stall
    (owner report, 2026-11-25)."""
    offset = {"value": 0.0}
    monkeypatch.setattr(
        clock,
        "wall",
        lambda: WALL_BASE + asyncio.get_running_loop().time() + offset["value"],
    )
    monkeypatch.setattr(
        clock,
        "boottime",
        lambda: 1_000.0 + asyncio.get_running_loop().time() + offset["value"],
    )
    monkeypatch.setattr(
        clock, "monotonic", lambda: 1_000.0 + asyncio.get_running_loop().time()
    )
    fake_pw.script("mic", feed_blocks(1), feed_blocks(20))
    fake_pw.script("sys", feed_blocks(1), feed_blocks(20))
    flushed: list[str] = []
    original = service.Health.flush

    def record(self, active, now, *, force=False):
        flushed.extend(item.code for item in active)
        return original(self, active, now, force=force)

    monkeypatch.setattr(service.Health, "flush", record)

    async def suspend() -> None:
        await clock.sleep(0.5)
        offset["value"] = 600.0

    task = asyncio.create_task(suspend())
    await run_capture(
        tmp_path,
        seconds=1.5,
        fake_pw=fake_pw,
        fake_source=fake_source,
        settings=config(stall_restart_s=2.0, stall_error_s=60.0),
    )
    await task
    assert "capture-stalled" not in flushed
