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
