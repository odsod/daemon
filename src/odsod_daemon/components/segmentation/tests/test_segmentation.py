import hashlib
import json
import wave
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from odsod_daemon.components.segmentation.config import Settings, Speech
from odsod_daemon.components.segmentation.cutter import Cutter
from odsod_daemon.components.segmentation.mask import (
    DICTATION_GUARD,
    DICTATION_STALE,
    read_limit,
)
from odsod_daemon.components.segmentation.runner import ChannelRunner
from odsod_daemon.components.segmentation.vad import MODEL, MODEL_SHA256, Vad
from odsod_daemon.lib import audio, clock, streams

AUDIO = Path(__file__).resolve().parents[5] / "tests/testdata/audio"


def setup_audio(root, name="sv-udhr-article1", channel="sys"):
    (root / "config/config.json").write_text(
        json.dumps(
            {
                "common": {
                    "inference": {
                        "whisper_url": "http://localhost:8178/v1/audio/transcriptions",
                        "llama_url": "http://localhost:8179/v1/chat/completions",
                    }
                }
            }
        )
    )
    start = clock.utc_now().replace(minute=0, second=0, microsecond=0)
    with wave.open(str(AUDIO / f"{name}.wav")) as wav:
        pcm = wav.readframes(wav.getnframes())
    path = audio.hour_file(root / "state", channel, start)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pcm)
    return start, start + timedelta(seconds=len(pcm) / 32000)


def test_model_shapes_and_pin():
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == MODEL_SHA256
    vad = Vad()
    with wave.open(str(AUDIO / "sv-udhr-article1.wav")) as wav:
        samples = wav.readframes(wav.getnframes())
    probabilities = [
        vad.probability(samples[i : i + 1024]) for i in range(0, len(samples), 1024)
    ]
    assert max(probabilities) > 0.5
    assert vad.state.shape == (2, 1, 128)
    assert vad.context.shape == (1, 64)
    assert vad.probability(bytes(1024)) == 0
    assert not np.any(vad.state)


@pytest.mark.parametrize("speech_ms,expected", [(100, 0), (300, 1)])
def test_cutter_minimum_and_pads(speech_ms, expected):
    cutter = Cutter(Settings(min_speech_ms=250, min_silence_ms=100, pad_end_ms=50))
    cuts = []
    for i in range(100):
        cuts += cutter.feed(
            i / 100, (i + 1) / 100, 0.9 if 20 <= i < 20 + speech_ms / 10 else 0
        )
    assert len(cuts) == expected
    if cuts:
        assert cuts[0].start == 0
        assert cuts[0].end == pytest.approx(0.55)


def test_forced_cut_and_boundary():
    cutter = Cutter(Settings(max_s=1, min_speech_ms=0, pad_start_ms=0))
    cuts = []
    for i in range(10):
        cuts += cutter.feed(i / 10, (i + 1) / 10, 0.6 if i == 7 else 0.9)
    assert cuts[0].reason == "forced"
    assert cuts[0].end == 0.7
    tail = cutter.boundary(1, "mask")
    assert tail[0].start == cuts[0].end
    assert tail[0].reason == "mask"


def test_mask_budget_and_stale():
    assert DICTATION_GUARD >= 0.3 + 0.35 + 0.15 + 0.2
    assert DICTATION_STALE >= 120 + 10
    status = {
        "mode": "dictating",
        "since": "2026-11-23T10:00:00Z",
        "audio_start": "2026-11-23T10:00:01Z",
    }
    now = clock.parse_iso("2026-11-23T10:00:03Z").timestamp()
    assert read_limit(now, now, status, once=False) == now - 2
    assert (
        read_limit(now + 200, now + 200, status, once=False)
        == now + 200 - DICTATION_GUARD
    )
    assert read_limit(now, now, status, once=True) == now


def test_drain_restart_and_mask(temp_root):
    start, end = setup_audio(temp_root)
    runner = ChannelRunner("sys", Speech())
    runner.advance(once=True)
    directory = temp_root / "state/utterances/ambient"
    before = streams.read_day(streams.day_path(directory, clock.utc_now().date()))
    assert before
    ChannelRunner("sys", Speech()).advance(once=True)
    assert (
        streams.read_day(streams.day_path(directory, clock.utc_now().date())) == before
    )
    assert (
        abs(
            clock.parse_iso(
                streams.read_day(
                    streams.day_path(
                        temp_root / "state/coverage", clock.utc_now().date()
                    )
                )[-1]["end"]
            ).timestamp()
            - end.timestamp()
        )
        < 0.001
    )
    setup_audio(temp_root, channel="mic")
    streams.append(
        streams.day_path(temp_root / "state/utterances/dictation", start.date()),
        {"id": "dic-test", "start": clock.iso(start), "end": clock.iso(end)},
    )
    ChannelRunner("mic", Speech()).advance(once=True)
    assert all(
        r["channel"] != "mic"
        for r in streams.read_day(streams.day_path(directory, start.date()))
    )


@pytest.mark.parametrize("name", ["silence", "noise-fan", "noise-room"])
def test_quiet_fixtures(temp_root, name):
    setup_audio(temp_root, name)
    ChannelRunner("sys", Speech()).advance(once=True)
    assert not list((temp_root / "state/utterances/ambient").glob("*.jsonl"))


def test_crash_after_utterance_before_coverage(temp_root, monkeypatch):
    setup_audio(temp_root)
    runner = ChannelRunner("sys", Speech())
    original = runner.cover

    def crash(end):
        raise RuntimeError("kill after utterance")

    monkeypatch.setattr(runner, "cover", crash)
    with pytest.raises(RuntimeError):
        runner.advance(once=True)
    monkeypatch.setattr(runner, "cover", original)
    ChannelRunner("sys", Speech()).advance(once=True)
    rows = streams.read_day(
        streams.day_path(temp_root / "state/utterances/ambient", clock.utc_now().date())
    )
    assert len(rows) == len({r["id"] for r in rows})


def test_live_hold_then_idle_reads_masks_synchronously(temp_root):
    start, end = setup_audio(temp_root, channel="mic")
    runner = ChannelRunner("mic", Speech())
    status = temp_root / "run/status.json"
    # Hold exactly at the start. The audio is older than the wall-clock guard.
    status.write_text(
        json.dumps(
            {"mode": "dictating", "since": clock.iso(), "audio_start": clock.iso(start)}
        )
    )
    runner.advance(once=False)
    assert runner.cursor == start.timestamp()
    streams.append(
        streams.day_path(temp_root / "state/utterances/dictation", start.date()),
        {"id": "dic-held", "start": clock.iso(start), "end": clock.iso(end)},
    )
    status.write_text(json.dumps({"mode": "idle", "since": clock.iso()}))
    # No follow notification is delivered; advance must read the mask itself.
    runner.advance(once=False)
    assert not list((temp_root / "state/utterances/ambient").glob("*.jsonl"))


def test_capture_guard_and_idle_close(temp_root, monkeypatch):
    _start, end = setup_audio(temp_root, channel="mic")
    runner = ChannelRunner("mic", Speech())
    monkeypatch.setattr(clock, "wall", lambda: end.timestamp() + 0.1)
    runner.advance(once=False)
    assert runner.cursor is not None
    assert runner.cursor <= end.timestamp() - 1.1
    monkeypatch.setattr(clock, "wall", lambda: end.timestamp() + DICTATION_GUARD + 1)
    runner.advance(once=False)
    assert runner.cursor is not None
    assert runner.cursor <= end.timestamp()
    runner.last_advance -= 4
    runner.advance(once=False)
    assert abs(runner.last_covered - end.timestamp()) < 0.001


def test_zero_hole_separates_speech(temp_root, monkeypatch):
    start, _ = setup_audio(temp_root)
    path = audio.hour_file(temp_root / "state", "sys", start)
    speech = np.full(16000, 3000, dtype="<i2").tobytes()
    path.write_bytes(speech + bytes(32000) + speech)
    monkeypatch.setattr(Vad, "probability", lambda self, pcm: 0.9)
    ChannelRunner("sys", Speech()).advance(once=True)
    rows = streams.read_day(
        streams.day_path(temp_root / "state/utterances/ambient", start.date())
    )
    assert len(rows) == 2
    assert clock.parse_iso(rows[0]["end"]) <= start + timedelta(seconds=1.024)
    assert clock.parse_iso(rows[1]["start"]) >= start + timedelta(seconds=1.98)


def test_hour_of_zeros_skips_model(temp_root, monkeypatch):
    start, _ = setup_audio(temp_root, "silence")
    path = audio.hour_file(temp_root / "state", "sys", start)
    with path.open("wb") as handle:
        handle.truncate(3600 * 32000)

    def no_inference(self, pcm):
        pytest.fail("zeros reached the model")

    monkeypatch.setattr(Vad, "probability", no_inference)
    ChannelRunner("sys", Speech()).advance(once=True)
    assert not list((temp_root / "state/utterances/ambient").glob("*.jsonl"))


@pytest.mark.looptime(False)
async def test_channels_advance_independently(temp_root, monkeypatch):
    import threading

    from odsod_daemon.components.segmentation.runner import run

    setup_audio(temp_root)
    sys_started = threading.Event()

    def advance(self, *, once):
        if self.channel == "mic":
            assert sys_started.wait(timeout=1), "sys waited behind mic"
        else:
            sys_started.set()

    monkeypatch.setattr(ChannelRunner, "advance", advance)
    await run(Speech(), once=True)


async def test_health_heartbeat_preserves_faults(temp_root, monkeypatch):
    from odsod_daemon.components.segmentation.runner import _heartbeat
    from odsod_daemon.lib import healthfile

    file = healthfile.HealthFile(temp_root / "run/health/pipeline.json", "pipeline")
    file.set("inference-unreachable", "down", key="whisper")
    file.rewrite()
    slept = []

    class StopHeartbeat(Exception):
        pass

    async def sleep(seconds):
        slept.append(seconds)
        raise StopHeartbeat

    monkeypatch.setattr(clock, "sleep", sleep)
    with pytest.raises(StopHeartbeat):
        await _heartbeat()
    assert slept == [60]
    faults = json.loads(file.path.read_text())["faults"]
    assert [f["key"] for f in faults] == ["whisper"]


def test_english_drain_keeps_sample_alignment(temp_root):
    _start, end = setup_audio(temp_root, "en-study-in-scarlet", "mic")
    runner = ChannelRunner("mic", Speech())
    runner.advance(once=True)
    assert abs(runner.last_covered - end.timestamp()) < 0.001
