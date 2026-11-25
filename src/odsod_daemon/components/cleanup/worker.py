"""Independent dictation and ambient cleanup lanes."""

import asyncio

from odsod_daemon.components.cleanup import filters, guard, prompt
from odsod_daemon.components.cleanup.contract import TextRecord
from odsod_daemon.components.cleanup.language import code
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.transcription.host import (
    Host,
    HostUnavailable,
    InputFailed,
    fingerprint,
)
from odsod_daemon.components.transcription.queue import Inbox, pending, records
from odsod_daemon.lib import clock, config, glossary, inference, paths, power, streams


async def cleanup(
    record: dict, speech: Speech, host: Host, *, once: bool
) -> TextRecord:
    dic = record["channel"] == "dic"
    common = config.load_common()
    entries = glossary.current()
    terms = glossary.terms(entries)
    system, digest = prompt.render(dic, speech, terms)
    heard = record.get("text") or ""
    source = filters.fillers(heard) if dic else heard
    result = TextRecord(
        ts=clock.iso(),
        input=record["input"],
        outcome=record["outcome"],
        text="",
        channel=record["channel"],
        start=record["start"],
        end=record["end"],
        language=code(record.get("language")),
        ms=0,
        prompt=digest,
        setup=fingerprint(
            {
                "url": common.inference.llama_url,
                "model": "default",
                "prompt": digest,
                "temperature": 0,
                "enable_thinking": False,
                "language_pin": True,
                "speech": speech.model_dump(),
            }
        ),
    )
    if result.outcome != "ok":
        return result
    if (
        not source
        or filters.phantom(source, speech.phantoms)
        or filters.glossary_echo(source, terms)
    ):
        result.outcome = "empty"
        return result

    async def wait_for_power() -> None:
        began = clock.monotonic()
        while (
            inference.is_loopback(common.inference.llama_url) and not power.on_mains()
        ):
            if once and clock.monotonic() - began >= 60:
                raise HostUnavailable("on battery; work remains pending")
            await clock.sleep(2)

    await wait_for_power()
    began = clock.monotonic()
    timeout_s = speech.dictation.cleanup_timeout_ms / 1000 if dic else None
    client = inference.LlamaClient(common.inference.llama_url, timeout_s=180)

    async def request():
        return await client.complete(
            prompt.messages(
                system,
                source,
                result.language or "und",
                glossary.hints(glossary.relevant(entries, source)),
            ),
            max_tokens=max(64, 2 * len(source) // 3),
            temperature=0,
        )

    try:
        async with clock.timeout(timeout_s):
            reply, _ = await host.call(
                request,
                attempts=speech.attempts,
                once=once,
                raw_on_host=dic,
                before_request=wait_for_power,
            )
        reply = guard.clean(reply)
        if not reply:
            if dic:
                result.raw, result.raw_reason, result.text = True, "llm-empty", source
            else:
                result.outcome = "empty"
        else:
            why = guard.reason(source, reply, result.language)
            if why:
                result.raw, result.raw_reason, result.text = True, why, source
            else:
                result.text = reply
                if reply != heard:
                    result.heard = heard
    except TimeoutError, HostUnavailable:
        if not dic:
            raise
        result.raw, result.raw_reason, result.text = True, "timeout", source
    except InputFailed as error:
        result.outcome, result.error = "failed", str(error)
    result.ts = clock.iso()
    result.ms = round((clock.monotonic() - began) * 1000)
    return result


async def lane(speech: Speech, dictation: bool, *, once: bool) -> None:
    state = paths.roots().state
    source = state / "asr" / speech.backend
    destination = state / "text"
    host = Host("llama")
    async with Inbox([source]) as inbox:
        while True:
            inbox.prepare()
            inputs = [
                r for r in records(source) if (r["channel"] == "dic") == dictation
            ]
            todo = pending(inputs, records(destination), field="input")
            if not todo:
                if once:
                    return
                await inbox.wait()
                continue
            result = await cleanup(todo[0], speech, host, once=once)
            streams.append(
                streams.day_path(destination, clock.utc_now().date()),
                result.model_dump(mode="json"),
            )


async def run(speech: Speech, *, once: bool = False) -> None:
    # ADR-0024: a satellite cleans only its dictation; the base does ambient.
    satellite = config.load_common().role == "satellite"
    async with asyncio.TaskGroup() as group:
        for dictation in (True,) if satellite else (True, False):
            group.create_task(lane(speech, dictation, once=once))
