"""A minimal whisper-server compatible endpoint: one request per connection."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
import wave
from collections.abc import Awaitable, Callable

import numpy as np

from odsod_daemon.components.parakeet.model import NAME, NotReady

PATH = "/v1/audio/transcriptions"
MAX_BODY = 32 * 1024 * 1024
HEAD_TIMEOUT_S = 10
BODY_TIMEOUT_S = 30
_FILE_FIELD = re.compile(rb'(?<![A-Za-z])name="file"')
REASONS = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    413: "Payload Too Large",
    500: "Internal Server Error",
    503: "Service Unavailable",
}

Transcribe = Callable[[np.ndarray], Awaitable[str]]


class BadRequest(ValueError):
    pass


def audio_file(content_type: str, body: bytes) -> bytes:
    """The bytes of the multipart field `file`."""
    kind, _, params = content_type.partition(";")
    if kind.strip().lower() != "multipart/form-data":
        raise BadRequest("want multipart/form-data")
    boundary = None
    for param in params.split(";"):
        key, _, value = param.strip().partition("=")
        if key.lower() == "boundary":
            boundary = value.strip().strip('"')
    if not boundary:
        raise BadRequest("no multipart boundary")
    for part in body.split(b"--" + boundary.encode("latin-1")):
        head, sep, content = part.partition(b"\r\n\r\n")
        if sep and _FILE_FIELD.search(head):
            return content.removesuffix(b"\r\n")
    raise BadRequest("no field 'file'")


def samples(data: bytes) -> np.ndarray:
    """16 kHz mono 16-bit WAV to float32 in [-1, 1)."""
    try:
        with wave.open(io.BytesIO(data)) as reader:
            shape = (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
            )
            if shape != (1, 2, 16000):
                raise BadRequest("want 16 kHz mono 16-bit WAV")
            frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as error:
        raise BadRequest(f"bad WAV: {error}") from error
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768


def response(status: int, payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    head = (
        f"HTTP/1.1 {status} {REASONS[status]}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    )
    return head.encode("latin-1") + body


async def reply(reader: asyncio.StreamReader, transcribe: Transcribe) -> bytes:
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT_S)
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            key, sep, value = line.partition(":")
            if sep:
                headers[key.strip().lower()] = value.strip()
        if method != "POST" or target.split("?", 1)[0] != PATH:
            return response(404, {"error": "not found"})
        length = int(headers.get("content-length", "0"))
        if length > MAX_BODY:
            return response(413, {"error": "body too large"})
        body = await asyncio.wait_for(reader.readexactly(length), BODY_TIMEOUT_S)
        pcm = samples(audio_file(headers.get("content-type", ""), body))
        text = await transcribe(pcm)
    except BadRequest as error:
        return response(400, {"error": str(error)})
    except ValueError:
        return response(400, {"error": "bad request"})
    except NotReady as error:
        return response(503, {"error": str(error)})
    return response(200, {"text": text, "language": "en", "model": NAME})


def handler(transcribe: Transcribe):
    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            writer.write(await reply(reader, transcribe))
            await writer.drain()
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
            ConnectionError,
        ):
            pass
        except Exception:
            with contextlib.suppress(ConnectionError):
                writer.write(response(500, {"error": "internal error"}))
                await writer.drain()
        finally:
            writer.close()

    return handle
