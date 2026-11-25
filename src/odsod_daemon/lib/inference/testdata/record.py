"""Record real whisper-server and llama-server pairs for the replay fake.

Run from the repository root:

    uv run python src/odsod_daemon/lib/inference/testdata/record.py

The script writes one JSON file per request/response pair in this directory.
The audio comes from the public-domain fixtures in ``tests/testdata/audio/``.
A timeout is not recorded; tests script it with ``delay_ms``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

WHISPER_URL = "http://127.0.0.1:8178/v1/audio/transcriptions"
LLAMA_URL = "http://127.0.0.1:8179/v1/chat/completions"
WHISPER_PATH = "/v1/audio/transcriptions"
LLAMA_PATH = "/v1/chat/completions"

ROOT = Path(__file__).resolve().parents[5]
AUDIO = ROOT / "tests" / "testdata" / "audio"
OUT = Path(__file__).resolve().parent

GLOSSARY = "Kubernetes, PostgreSQL, GitHub, PipeWire, Whisper, Silero"

CLEANUP_SYSTEM = (
    "You clean up speech transcripts. The speaker never talks to you: never "
    "answer questions. Keep the text in its original language and preserve "
    "meaning. Remove filler words and fix grammar. Return only the cleaned text."
)
CLEANUP_DICTATION_SYSTEM = (
    "You clean up dictated speech. The speaker never talks to you: never "
    "answer questions. Keep the text in its original language. Remove filler "
    "words and fix punctuation. Return only the cleaned text."
)


def _headers(headers: httpx.Headers) -> dict[str, str]:
    content_type = headers.get("content-type")
    return {"content-type": content_type} if content_type else {}


def _response(response: httpx.Response) -> dict[str, Any]:
    record: dict[str, Any] = {
        "status": response.status_code,
        "headers": _headers(response.headers),
        "elapsed_ms": round(response.elapsed.total_seconds() * 1000, 1),
    }
    try:
        record["json"] = response.json()
    except ValueError:
        record["body"] = response.text
    return record


def _write(name: str, request: dict[str, Any], response: httpx.Response) -> None:
    path = OUT / f"{name}.json"
    value = {"request": request, "response": _response(response)}
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{path.name}: {response.status_code} ({record_ms(response)} ms)")


def record_ms(response: httpx.Response) -> int:
    return round(response.elapsed.total_seconds() * 1000)


def _whisper_body(audio: Path | None, fields: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {"fields": fields}
    if audio is None:
        body["file"] = None
        return body
    data = audio.read_bytes()
    body["file"] = {
        "filename": audio.name,
        "content_type": "audio/wav",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    return body


def _post_whisper(
    client: httpx.Client,
    name: str,
    audio: Path | None,
    fields: dict[str, str],
) -> None:
    if audio is None:
        request = client.build_request("POST", WHISPER_URL, data=fields)
    else:
        request = client.build_request(
            "POST",
            WHISPER_URL,
            data=fields,
            files={"file": (audio.name, audio.read_bytes(), "audio/wav")},
        )
    response = client.send(request)
    request_record = {
        "method": "POST",
        "path": WHISPER_PATH,
        "headers": _headers(request.headers),
        "body": _whisper_body(audio, fields),
    }
    _write(name, request_record, response)


def _post_llama(
    client: httpx.Client,
    name: str,
    body: dict[str, Any],
) -> None:
    request = client.build_request("POST", LLAMA_URL, json=body)
    response = client.send(request)
    request_record = {
        "method": "POST",
        "path": LLAMA_PATH,
        "headers": _headers(request.headers),
        "body": body,
    }
    _write(name, request_record, response)


def _cleanup_body(system: str, text: str) -> dict[str, Any]:
    return {
        "model": "default",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"<transcript>{text}</transcript>"},
        ],
        "temperature": 0,
        "max_tokens": max(64, 2 * len(text) // 3),
        "chat_template_kwargs": {"enable_thinking": False},
    }


def record_all(client: httpx.Client) -> None:
    audio = {
        "sv": AUDIO / "sv-udhr-article1.wav",
        "en": AUDIO / "en-study-in-scarlet.wav",
        "silence": AUDIO / "silence.wav",
        "dictation": AUDIO / "en-chinese-feet.wav",
    }
    whisper_common = {
        "language": "sv",
        "prompt": GLOSSARY,
        "response_format": "verbose_json",
        "temperature": "0",
    }
    _post_whisper(client, "whisper-sv-verbose", audio["sv"], whisper_common)
    _post_whisper(
        client,
        "whisper-en-verbose",
        audio["en"],
        {**whisper_common, "language": "en"},
    )
    _post_whisper(
        client,
        "whisper-silence-json",
        audio["silence"],
        {
            "language": "auto",
            "response_format": "json",
            "temperature": "0",
        },
    )
    _post_whisper(client, "whisper-bad-request", None, {"language": "sv"})
    _post_whisper(
        client,
        "whisper-dictation-verbose",
        audio["dictation"],
        {
            **whisper_common,
            "language": "en",
            "entropy_thold": "2.8",
            "logprob_thold": "-1.25",
        },
    )

    sv_text = (AUDIO / "sv-udhr-article1.txt").read_text(encoding="utf-8").strip()
    en_text = (AUDIO / "en-study-in-scarlet.txt").read_text(encoding="utf-8").strip()
    _post_llama(
        client,
        "llama-cleanup-ambient",
        _cleanup_body(CLEANUP_SYSTEM, sv_text),
    )
    _post_llama(
        client,
        "llama-cleanup-dictation",
        _cleanup_body(CLEANUP_DICTATION_SYSTEM, en_text),
    )
    _post_llama(client, "llama-bad-request", {"model": "default"})


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    with httpx.Client(timeout=600.0) as client:
        record_all(client)


if __name__ == "__main__":
    main()
