"""ADR-0022: the parakeet endpoint, model pin and service."""

import asyncio
import io
import json
import wave

import httpx
import numpy as np
import pytest

from odsod_daemon.components.parakeet import endpoint, model, service
from odsod_daemon.components.segmentation.config import Parakeet, Speech
from odsod_daemon.lib import inference

pytestmark = pytest.mark.looptime(False)


def wav(seconds=0.5, rate=16000, channels=1) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x40" * int(seconds * rate) * channels)
    return out.getvalue()


def multipart(audio: bytes) -> tuple[str, bytes]:
    request = httpx.Request(
        "POST",
        "http://x/",
        files={"file": ("filename.wav", audio, "audio/wav")},
        data={"language": "en", "prompt": 'name="file"'},
    )
    return request.headers["content-type"], request.read()


def test_audio_file_reads_the_file_field_exactly():
    audio = wav() + b"\r\n--tail\r\n\r\n"
    content_type, body = multipart(audio)
    assert endpoint.audio_file(content_type, body) == audio


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "multipart/form-data", "multipart/form-data; boundary=x"],
)
def test_audio_file_rejects(content_type):
    with pytest.raises(endpoint.BadRequest):
        endpoint.audio_file(content_type, b"--x\r\n\r\nnothing")


def test_samples_scale_and_format():
    pcm = endpoint.samples(wav(0.25))
    assert pcm.dtype == np.float32 and len(pcm) == 4000 and pcm[0] == 0.5
    for bad in (wav(rate=8000), wav(channels=2), b"not a wav"):
        with pytest.raises(endpoint.BadRequest):
            endpoint.samples(bad)


async def serve(transcribe):
    server = await asyncio.start_server(endpoint.handler(transcribe), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}{endpoint.PATH}"


async def test_whisper_client_gets_text_from_the_endpoint():
    seen = []

    async def transcribe(pcm):
        seen.append(len(pcm))
        return "Hello there."

    server, url = await serve(transcribe)
    async with server:
        client = inference.WhisperClient(url, timeout_s=5)
        reply = await client.transcribe(wav(), fields={"language": "en"})
    assert reply.text == "Hello there." and reply.language == "en"
    assert (reply.model_extra or {})["model"] == model.NAME and seen == [8000]


async def test_errors_map_to_status():
    async def loading(pcm):
        raise model.NotReady("model loading")

    server, url = await serve(loading)
    async with server, httpx.AsyncClient() as client:
        content_type, body = multipart(wav())
        headers = {"content-type": content_type}
        assert (
            await client.post(url, content=body, headers=headers)
        ).status_code == 503
        bad = multipart(b"no wav")
        assert (
            await client.post(url, content=bad[1], headers={"content-type": bad[0]})
        ).status_code == 400
        assert (await client.get(url)).status_code == 404
        other = url.replace(endpoint.PATH, "/other")
        assert (
            await client.post(other, content=body, headers=headers)
        ).status_code == 404


async def test_recognizer_not_ready_and_short_audio():
    recognizer = model.Recognizer()
    with pytest.raises(model.NotReady):
        await recognizer(np.zeros(16000, np.float32))

    class Fake:
        def recognize(self, samples):
            return " text "

    recognizer.model = Fake()
    assert await recognizer(np.zeros(100, np.float32)) == ""
    assert await recognizer(np.zeros(16000, np.float32)) == "text"


def test_pin_covers_the_model_files():
    assert set(model.FILES) == {
        "config.json",
        "vocab.txt",
        "decoder_joint-model.int8.onnx",
        "encoder-model.int8.onnx",
    }
    assert model.REVISION in model.BASE_URL
    assert all(pin.url.startswith(model.BASE_URL) for pin in model.PINS)


def test_listen_must_be_private():
    with pytest.raises(ValueError):
        Parakeet(listen=["0.0.0.0"])
    assert Parakeet(listen=["127.0.0.1", "100.79.24.22"]).port == 8180


async def test_disabled_does_nothing(temp_root, monkeypatch):
    async def no_load(*args):
        pytest.fail("disabled server loaded a model")

    monkeypatch.setattr(model.Recognizer, "load", no_load)
    task = asyncio.create_task(service.run(Speech()))
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    await service.run(Speech(parakeet=Parakeet(enabled=True)), once=True)


async def test_bind_failure_warns_after_a_minute(temp_root, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(service.clock, "monotonic", lambda: now[0])

    async def sleep(seconds):
        now[0] += seconds
        if now[0] > service.BIND_WARN_S + 10:
            raise asyncio.CancelledError

    monkeypatch.setattr(service.clock, "sleep", sleep)

    async def refuse(*args, **kwargs):
        raise OSError("Cannot assign requested address")

    monkeypatch.setattr(service.asyncio, "start_server", refuse)
    with pytest.raises(asyncio.CancelledError):
        await service.listen("100.79.24.22", 8180, model.Recognizer())
    faults = json.loads((temp_root / "run/health/pipeline.json").read_text())["faults"]
    assert [(f["code"], f["key"]) for f in faults] == [
        ("parakeet-unavailable", "listen-100.79.24.22")
    ]
