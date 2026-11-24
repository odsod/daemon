import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from odsod_daemon.components.cleanup.language import code
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.segmentation.tests.test_segmentation import setup_audio
from odsod_daemon.components.transcription.host import (
    Host,
    HostUnavailable,
    InputFailed,
    fault_kind,
)
from odsod_daemon.components.transcription.queue import pending
from odsod_daemon.components.transcription.request import fields, glossary_tail
from odsod_daemon.components.transcription.worker import run, transcribe
from odsod_daemon.lib import clock, inference, streams

DATA = Path(inference.__file__).parent / "testdata"


def utterance(start, end, channel="sys", ident="test"):
    return {
        "id": ident,
        "channel": channel,
        "start": clock.iso(start),
        "end": clock.iso(end),
    }


def test_order_and_fields():
    rows = [
        {"id": "ambient", "start": "1", "channel": "mic"},
        {"id": "dictation", "start": "2", "channel": "dic"},
    ]
    assert [r["id"] for r in pending(rows, [])] == ["dictation", "ambient"]
    assert pending(rows, [{"input": "dictation"}]) == rows[:1]
    assert glossary_tail(["first", "middle", "last"], 12) == "middle, last"
    assert glossary_tail(["last"], 0) == ""
    assert fields(True, Speech(), ["Silero"])["language"] == "en"
    assert "entropy_thold" not in fields(False, Speech(), [])


def test_recorded_languages():
    for name, expected in [("sv", "sv"), ("en", "en"), ("dictation", "en")]:
        record = json.loads((DATA / f"whisper-{name}-verbose.json").read_text())
        assert code(record["response"]["json"]["language"]) == expected
    assert code("sv") == "sv"
    assert code("NORWEGIAN") == "no"
    assert code(None) == "und"


@pytest.mark.parametrize(
    "status,kind",
    [
        (400, "reject"),
        (413, "reject"),
        (422, "reject"),
        (500, "input"),
        (501, "input"),
        (429, "host"),
        (502, "host"),
        (503, "host"),
        (504, "host"),
    ],
)
def test_fault_classification(status, kind):
    response = httpx.Response(
        status, request=httpx.Request("POST", "http://localhost/x")
    )
    assert (
        fault_kind(
            httpx.HTTPStatusError(
                "failure", request=response.request, response=response
            )
        )
        == kind
    )


async def test_hour_down_and_catch_up(temp_root):
    host = Host("whisper")
    calls = 0
    began = clock.monotonic()

    async def request():
        nonlocal calls
        calls += 1
        if clock.monotonic() - began < 3600:
            response = httpx.Response(
                503, request=httpx.Request("POST", "http://localhost/x")
            )
            raise httpx.HTTPStatusError(
                "busy", request=response.request, response=response
            )
        doc = json.loads((temp_root / "run/health/pipeline.json").read_text())
        assert doc["faults"][0]["key"] == "whisper"
        return "ok"

    result, attempts = await host.call(request, attempts=3, once=False)
    assert result == "ok" and attempts == 1 and calls > 100
    assert (
        json.loads((temp_root / "run/health/pipeline.json").read_text())["faults"] == []
    )


async def test_once_host_down_stays_pending(temp_root):
    async def request():
        raise httpx.ConnectError("refused")

    with pytest.raises(HostUnavailable):
        await Host("whisper").call(request, attempts=3, once=True)
    assert not list((temp_root / "state/asr").glob("**/*.jsonl"))


@pytest.mark.parametrize("status,expected", [(400, 1), (500, 3)])
async def test_input_attempts(temp_root, status, expected):
    calls = 0

    async def request():
        nonlocal calls
        calls += 1
        response = httpx.Response(
            status, request=httpx.Request("POST", "http://localhost/x")
        )
        raise httpx.HTTPStatusError("bad", request=response.request, response=response)

    with pytest.raises(InputFailed) as failure:
        await Host("whisper").call(request, attempts=3, once=True)
    assert calls == expected == failure.value.attempts


@pytest.mark.looptime(False)
async def test_recorded_response_and_fallback(temp_root):
    start, end = setup_audio(temp_root)
    pair = json.loads((DATA / "whisper-sv-verbose.json").read_text())
    wrong = json.loads(json.dumps(pair))
    wrong["response"]["json"]["language"] = "norwegian"
    server = inference.ReplayServer([wrong, pair])
    try:
        path = temp_root / "config/config.json"
        conf = json.loads(path.read_text())
        conf["common"]["inference"]["whisper_url"] = server.url + inference.WHISPER_PATH
        path.write_text(json.dumps(conf))
        result = await transcribe(
            utterance(start, end), Speech(), Host("whisper"), once=True
        )
        assert (
            result.outcome == "ok" and result.language == "sv" and result.attempts == 2
        )
        assert b"\r\nsv\r\n" in server.requests[1]["body"]
        assert result.text
    finally:
        server.close()


async def test_expired_and_dictation_gate(temp_root):
    start, end = setup_audio(temp_root, "silence", "mic")
    result = await transcribe(
        utterance(start, end, "dic"), Speech(), Host("whisper"), once=True
    )
    assert result.outcome == "empty" and result.attempts == 0 and result.gate == 0
    result = await transcribe(
        utterance(start - timedelta(hours=1), start, "sys"),
        Speech(),
        Host("whisper"),
        once=True,
    )
    assert result.outcome == "expired"


async def test_battery_loopback_waits(temp_root, monkeypatch):
    start, end = setup_audio(temp_root)
    streams.append(
        streams.day_path(temp_root / "state/utterances/ambient", start.date()),
        utterance(start, end),
    )
    monkeypatch.setattr(
        "odsod_daemon.components.transcription.worker.power.on_mains", lambda: False
    )
    with pytest.raises(HostUnavailable, match="battery"):
        await run(Speech(), once=True)
    assert not list((temp_root / "state/asr").glob("**/*.jsonl"))


async def test_battery_tailnet_sends_request(temp_root, monkeypatch):
    start, end = setup_audio(temp_root)
    conf_path = temp_root / "config/config.json"
    conf = json.loads(conf_path.read_text())
    conf["common"]["inference"]["whisper_url"] = (
        "http://100.64.1.2:8178/v1/audio/transcriptions"
    )
    conf_path.write_text(json.dumps(conf))
    monkeypatch.setattr(
        "odsod_daemon.components.transcription.worker.power.on_mains", lambda: False
    )
    called = []

    async def transcribe(self, audio, **kwargs):
        called.append(self.url)
        return inference.WhisperResponse(text="Hej", language="swedish")

    monkeypatch.setattr(inference.WhisperClient, "transcribe", transcribe)
    streams.append(
        streams.day_path(temp_root / "state/utterances/ambient", start.date()),
        utterance(start, end),
    )
    await run(Speech(), once=True)
    assert called == [conf["common"]["inference"]["whisper_url"]]


@pytest.mark.parametrize(
    "exception,kind",
    [
        (httpx.ConnectTimeout("connect"), "host"),
        (httpx.ReadError("reset"), "host"),
        (httpx.ReadTimeout("accepted"), "input"),
        (ValueError("bad reply"), "reject"),
    ],
)
def test_transport_faults(exception, kind):
    assert fault_kind(exception) == kind


async def test_new_dictation_goes_before_ambient_retry(temp_root, monkeypatch):
    start, end = setup_audio(temp_root)
    setup_audio(temp_root, "en-chinese-feet", "mic")
    ambient = utterance(start, end, "sys", "ambient")
    dic = utterance(start, end, "dic", "dictation")
    streams.append(
        streams.day_path(temp_root / "state/utterances/ambient", start.date()), ambient
    )
    calls = []

    async def response(self, audio, *, fields, **kwargs):
        calls.append(fields["language"])
        if len(calls) == 1:
            streams.append(
                streams.day_path(
                    temp_root / "state/utterances/dictation", start.date()
                ),
                dic,
            )
            reply = httpx.Response(500, request=httpx.Request("POST", self.url))
            raise httpx.HTTPStatusError("retry", request=reply.request, response=reply)
        return inference.WhisperResponse(text="Words", language="english")

    monkeypatch.setattr(inference.WhisperClient, "transcribe", response)
    monkeypatch.setattr(
        "odsod_daemon.components.transcription.worker.presence",
        lambda *args: (True, 0.9),
    )
    # Dictation uses the same time range as ambient; extend its buffer for this check.
    mic = temp_root / "state/audio/mic"
    sys = temp_root / "state/audio/sys"
    for file in sys.glob("*.pcm"):
        (mic / file.name).write_bytes(file.read_bytes())
    await run(Speech(), once=True)
    assert calls == ["auto", "en", "auto"]


@pytest.mark.parametrize("missing", [False, True])
async def test_live_audio_waits_for_flush(temp_root, monkeypatch, missing):
    from odsod_daemon.lib import audio

    setup_audio(temp_root)
    start = clock.utc_now().replace(microsecond=0)
    end = start + timedelta(seconds=0.15)
    path = audio.hour_file(temp_root / "state", "sys", start)
    if missing:
        path.unlink()
    else:
        path.write_bytes(b"")
    waited = []

    async def wait(state, channel, target):
        waited.append(target)
        path.write_bytes(
            bytes(round((end - audio.hour_start(start)).total_seconds() * 32000))
        )

    async def response(*args, **kwargs):
        assert waited == [end]
        return inference.WhisperResponse(text="Words", language="english")

    monkeypatch.setattr(audio, "wait_until", wait)
    monkeypatch.setattr(inference.WhisperClient, "transcribe", response)
    result = await transcribe(
        utterance(start, end), Speech(), Host("whisper"), once=False
    )
    assert result.outcome == "ok"


async def test_missing_old_hour_expires(temp_root, monkeypatch):
    setup_audio(temp_root)
    start = clock.utc_now() - timedelta(days=1)

    async def no_request(*args, **kwargs):
        pytest.fail("expired audio sent a request")

    monkeypatch.setattr(inference.WhisperClient, "transcribe", no_request)
    result = await transcribe(
        utterance(start, start + timedelta(seconds=1)),
        Speech(),
        Host("whisper"),
        once=False,
    )
    assert result.outcome == "expired"


async def test_dictation_url_runs_dictation_beside_ambient(temp_root, monkeypatch):
    """PRD dictation AC-27: a dictation never waits for an ambient request."""
    import asyncio

    start, end = setup_audio(temp_root)
    mic = temp_root / "state/audio/mic"
    mic.mkdir(parents=True, exist_ok=True)
    for file in (temp_root / "state/audio/sys").glob("*.pcm"):
        (mic / file.name).write_bytes(file.read_bytes())
    conf_path = temp_root / "config/config.json"
    conf = json.loads(conf_path.read_text())
    whisper_url = conf["common"]["inference"]["whisper_url"]
    dictation_url = "http://127.0.0.1:8180/v1/audio/transcriptions"
    conf["common"]["inference"]["dictation_url"] = dictation_url
    conf_path.write_text(json.dumps(conf))
    for kind, channel in (("ambient", "sys"), ("dictation", "dic")):
        streams.append(
            streams.day_path(temp_root / f"state/utterances/{kind}", start.date()),
            utterance(start, end, channel, kind),
        )
    dictated = asyncio.Event()
    calls = []

    async def response(self, audio, **kwargs):
        calls.append(self.url)
        if self.url == whisper_url:
            # Blocks until dictation is done: a shared loop would deadlock here.
            await asyncio.wait_for(dictated.wait(), 5)
            return inference.WhisperResponse(text="Ambient", language="english")
        dictated.set()
        return inference.WhisperResponse(text="Dictated", language="en")

    monkeypatch.setattr(inference.WhisperClient, "transcribe", response)
    monkeypatch.setattr(
        "odsod_daemon.components.transcription.worker.presence",
        lambda *args: (True, 0.9),
    )
    await run(Speech(), once=True)
    assert sorted(calls) == sorted([whisper_url, dictation_url])
    rows = [
        json.loads(line)
        for file in (temp_root / "state/asr/whisper").glob("*.jsonl")
        for line in file.read_text().splitlines()
    ]
    assert {r["input"]: r["text"] for r in rows} == {
        "ambient": "Ambient",
        "dictation": "Dictated",
    }
