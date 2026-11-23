"""One Whisper request at a time, with dictation first on every dequeue."""

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


def glossary() -> list[str]:
    path = paths.roots().config / "glossary.txt"
    return (
        [line.strip() for line in path.read_text().splitlines() if line.strip()]
        if path.exists()
        else []
    )


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
    request_fields = fields(dic, speech, glossary())
    setup = {
        "url": common.inference.whisper_url,
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
        common.inference.whisper_url,
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
    host = Host("whisper")

    async def wait_for_power() -> None:
        began = clock.monotonic()
        url = config.load_common().inference.whisper_url
        while inference.is_loopback(url) and not power.on_mains():
            if once and clock.monotonic() - began >= 60:
                raise HostUnavailable("on battery; work remains pending")
            await clock.sleep(2)

    def append(result: AsrRecord) -> None:
        streams.append(
            streams.day_path(output, clock.utc_now().date()),
            result.model_dump(mode="json"),
        )

    async def dictation_first() -> None:
        # Recheck before retries and the fallback request, not just on dequeue.
        await wait_for_power()
        while todo := pending(records(inputs[0]), records(output)):
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
