"""One request at a time per server, with dictation first on every dequeue.

With `dictation_url` set, dictation has its own loop and server (ADR-0022).
"""

import asyncio
from collections.abc import Awaitable, Callable

from odsod_daemon.components.cleanup.language import code
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.transcription.contract import AsrRecord
from odsod_daemon.components.transcription.host import (
    Host,
    HostUnavailable,
    InputFailed,
    fingerprint,
)
from odsod_daemon.components.transcription.presence import presence
from odsod_daemon.components.transcription.queue import Inbox, pending, records
from odsod_daemon.components.transcription.request import fields, wav
from odsod_daemon.lib import audio, clock, config, inference, paths, power, streams
from odsod_daemon.lib import glossary as lib_glossary


def glossary() -> list[str]:
    return lib_glossary.terms(lib_glossary.current())


def available(state, channel, start, end) -> bool:
    cursor = start
    while cursor < end:
        file = audio.hour_file(state, channel, cursor)
        stop = min(end, audio.hour_end(cursor))
        if not file.exists() and audio.hour_start(cursor) < audio.hour_start(
            clock.utc_now()
        ):
            return False
        cursor = stop
    return True


async def transcribe(
    record: dict,
    speech: Speech,
    host: Host,
    *,
    once: bool,
    before_request: Callable[[], Awaitable[None]] | None = None,
) -> AsrRecord:
    roots = paths.roots()
    dic = record["channel"] == "dic"
    common = config.load_common()
    url = common.inference.dictation() if dic else common.inference.whisper_url
    request_fields = fields(dic, speech, glossary())
    setup = {
        "url": url,
        "fields": request_fields,
        "speech": speech.model_dump(),
    }
    result = AsrRecord(
        ts=clock.iso(),
        input=record["id"],
        outcome="ok",
        text="",
        language="und",
        setup=fingerprint(setup),
        ms=0,
        attempts=0,
        channel=record["channel"],
        start=record["start"],
        end=record["end"],
    )
    start, end = clock.parse_iso(record["start"]), clock.parse_iso(record["end"])
    channel = "mic" if dic else record["channel"]
    if not available(roots.state, channel, start, end):
        result.outcome = "expired"
        return result
    covered = audio.covered_until(roots.state, channel)
    if covered is None or covered < end:
        if once:
            raise HostUnavailable("audio not yet flushed; work remains pending")
        await audio.wait_until(roots.state, channel, end)
    # Retention can remove an hour while the reader waits for capture.
    if not available(roots.state, channel, start, end):
        result.outcome = "expired"
        return result
    pcm = audio.cut(roots.state, channel, start, end)
    if dic:
        present, peak = presence(pcm, speech.dictation)
        result.gate = peak
        if not present:
            result.outcome = "empty"
            return result
    client = inference.WhisperClient(
        url,
        timeout_s=speech.dictation.timeout_s if dic else 60,
    )
    encoded = wav(pcm)
    began = clock.monotonic()
    try:
        response, attempts = await host.call(
            lambda: client.transcribe(encoded, fields=request_fields),
            attempts=speech.attempts,
            once=once,
            before_request=before_request,
        )
        result.attempts = attempts
        language = code(response.language)
        if (
            not dic
            and speech.ambient.language == "auto"
            and language not in speech.ambient.languages
        ):
            request_fields["language"] = speech.ambient.fallback_language
            response, attempts = await host.call(
                lambda: client.transcribe(encoded, fields=request_fields),
                attempts=speech.attempts,
                once=once,
                before_request=before_request,
            )
            result.attempts += attempts
        result.text = response.text.strip()
        result.language = code(response.language)
        result.setup = fingerprint(
            {**setup, "model": (response.model_extra or {}).get("model", "whisper")}
        )
        result.outcome = "ok" if result.text else "empty"
    except InputFailed as error:
        result.outcome, result.error, result.attempts = (
            "failed",
            str(error),
            error.attempts,
        )
    result.ms = round((clock.monotonic() - began) * 1000)
    result.ts = clock.iso()
    return result


async def run(speech: Speech, *, once: bool = False) -> None:
    roots = paths.roots()
    inputs = [roots.state / f"utterances/{kind}" for kind in ("dictation", "ambient")]
    output = roots.state / "asr" / speech.backend
    common = config.load_common()
    if common.role == "satellite":
        # ADR-0024: the base transcribes ambient audio; dictation stays here.
        inputs = inputs[:1]
    if common.inference.dictation_url is None:
        await serve(speech, inputs, output, Host("whisper"), "whisper_url", once=once)
        return
    if common.role == "satellite":
        await serve(
            speech, inputs, output, Host("parakeet"), "dictation_url", once=once
        )
        return
    async with asyncio.TaskGroup() as group:
        group.create_task(
            serve(
                speech, inputs[:1], output, Host("parakeet"), "dictation_url", once=once
            )
        )
        group.create_task(
            serve(speech, inputs[1:], output, Host("whisper"), "whisper_url", once=once)
        )


async def serve(
    speech: Speech,
    inputs: list,
    output,
    host: Host,
    key: str,
    *,
    once: bool,
) -> None:
    """Work through `inputs`; a dictation input always goes first."""

    async def wait_for_power() -> None:
        began = clock.monotonic()
        url = getattr(config.load_common().inference, key)
        while inference.is_loopback(url) and not power.on_mains():
            if once and clock.monotonic() - began >= 60:
                raise HostUnavailable("on battery; work remains pending")
            await clock.sleep(2)

    def append(result: AsrRecord) -> None:
        streams.append(
            streams.day_path(output, clock.utc_now().date()),
            result.model_dump(mode="json"),
        )

    dictation = [d for d in inputs if d.name == "dictation"]

    async def dictation_first() -> None:
        # Recheck before retries and the fallback request, not just on dequeue.
        await wait_for_power()
        while dictation and (todo := pending(records(dictation[0]), records(output))):
            append(
                await transcribe(
                    todo[0], speech, host, once=once, before_request=wait_for_power
                )
            )
        await wait_for_power()

    async with Inbox(inputs) as inbox:
        while True:
            inbox.prepare()
            todo = pending(
                [r for directory in inputs for r in records(directory)], records(output)
            )
            if not todo:
                if once:
                    return
                await inbox.wait()
                continue
            await wait_for_power()
            before = wait_for_power if todo[0]["channel"] == "dic" else dictation_first
            append(
                await transcribe(
                    todo[0], speech, host, once=once, before_request=before
                )
            )
