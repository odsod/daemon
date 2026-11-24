import asyncio
import json
from pathlib import Path

import httpx
import pytest

from odsod_daemon.components.cleanup import filters, guard, prompt
from odsod_daemon.components.cleanup.worker import cleanup, run
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.segmentation.tests.test_segmentation import setup_audio
from odsod_daemon.components.transcription.host import Host, health
from odsod_daemon.lib import clock, inference, streams


def asr(channel="sys", text="How many people live here?", outcome="ok", ident="test"):
    return {
        "input": ident,
        "channel": channel,
        "start": clock.iso(),
        "end": clock.iso(),
        "text": text,
        "outcome": outcome,
        "language": "english",
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ("THANKS for watching!", True),
        ("He said thanks for watching the children", False),
    ],
)
def test_phantoms(text, expected):
    assert filters.phantom(text, Speech().phantoms) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Kubernetes PostgreSQL GitHub", True),
        ("GitHub PostgreSQL Kubernetes", False),
        ("Kubernetes PostgreSQL", False),
        ("We use Kubernetes today, PostgreSQL tomorrow and GitHub next week", False),
        ("Kubernetes and PostgreSQL GitHub", True),
    ],
)
def test_glossary_echo(text, expected):
    assert (
        filters.glossary_echo(text, ["Kubernetes", "PostgreSQL", "GitHub"]) == expected
    )


@pytest.mark.parametrize(
    "source,reply,reason",
    [
        ("We have 12 people.", "We have people.", "guard-number"),
        ("We have 12 people.", "We have 12 people.", None),
        ("A long source sentence.", "Short", "guard-length"),
        ("12 12 are here", "12 are here", "guard-number"),
        # Live meeting 2026-11-24: the model translated English to Swedish.
        ("That's it for me.", "Det är det för mig.", "guard-overlap"),
        (
            "additional connected cars access, I think,",
            "Ytterligare tillgång till anslutna bilar, jag tror.",
            "guard-overlap",
        ),
        ("continue the good work.", "Fortsätt det goda arbetet.", "guard-overlap"),
        ("Just det, alltså inte alltid", "Precis så, alltså inte alltid", None),
        ("um so we we ship it on friday", "So we ship it on Friday.", None),
        ("på deras home-surf.", "På deras hemsida.", None),
    ],
)
def test_guards(source, reply, reason):
    assert guard.reason(source, reply) == reason
    assert guard.clean("<think>analysis</think>\u200bQuestion?") == "Question?"


def test_prompt_override_and_question(temp_root):
    text, digest = prompt.render(True, Speech(), ["Silero"])
    assert "Never answer questions" in text and "Silero" in text
    assert (
        prompt.messages(text, "Why?")[1]["content"] == "<transcript>Why?</transcript>"
    )
    path = temp_root / "config/prompts/cleanup.md"
    path.parent.mkdir()
    path.write_text("{{ glossary | join(', ') }}: {{ prompt_languages | join('/') }}")
    override, changed = prompt.render(False, Speech(), ["Whisper"])
    assert override == "Whisper: Swedish/English" and changed != digest


@pytest.mark.parametrize("outcome", ["empty", "expired", "failed"])
async def test_copy_through(temp_root, outcome):
    setup_audio(temp_root)
    result = await cleanup(asr(outcome=outcome), Speech(), Host("llama"), once=True)
    assert result.outcome == outcome and result.text == "" and not result.raw


async def test_no_request_for_filter(temp_root, monkeypatch):
    setup_audio(temp_root)

    async def no_request(*args, **kwargs):
        pytest.fail("filter sent request")

    monkeypatch.setattr(inference.LlamaClient, "complete", no_request)
    result = await cleanup(
        asr(text="Thanks for watching!"), Speech(), Host("llama"), once=True
    )
    assert result.outcome == "empty"


@pytest.mark.parametrize(
    "channel,reply,outcome,raw,reason",
    [
        ("sys", "", "empty", False, None),
        ("dic", "", "ok", True, "llm-empty"),
        ("dic", "How many people live here?", "ok", False, None),
        ("sys", "Short", "ok", True, "guard-length"),
    ],
)
async def test_replies(temp_root, monkeypatch, channel, reply, outcome, raw, reason):
    setup_audio(temp_root)

    async def complete(self, messages, **kwargs):
        assert "Never answer questions" in messages[0]["content"]
        return reply

    monkeypatch.setattr(inference.LlamaClient, "complete", complete)
    result = await cleanup(asr(channel), Speech(), Host("llama"), once=True)
    assert (result.outcome, result.raw, result.raw_reason) == (outcome, raw, reason)


async def test_dictation_timeout_and_keyed_fault(temp_root, monkeypatch):
    setup_audio(temp_root)
    health("whisper", down=True)

    async def slow(*args, **kwargs):
        await clock.sleep(2)
        return "late"

    monkeypatch.setattr(inference.LlamaClient, "complete", slow)
    began = clock.monotonic()
    result = await cleanup(asr("dic"), Speech(), Host("llama"), once=True)
    assert clock.monotonic() - began == pytest.approx(1)
    assert result.raw and result.raw_reason == "timeout"
    assert result.text == asr()["text"]

    async def success(*args, **kwargs):
        return asr()["text"]

    monkeypatch.setattr(inference.LlamaClient, "complete", success)
    await cleanup(asr(), Speech(), Host("llama"), once=True)
    faults = json.loads((temp_root / "run/health/pipeline.json").read_text())["faults"]
    assert [fault["key"] for fault in faults] == ["whisper"]


async def test_dictation_host_down_raw(temp_root, monkeypatch):
    setup_audio(temp_root)

    async def down(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(inference.LlamaClient, "complete", down)
    result = await cleanup(asr("dic"), Speech(), Host("llama"), once=True)
    assert result.raw and result.raw_reason == "timeout"


async def test_two_lanes(temp_root, monkeypatch):
    setup_audio(temp_root)
    ambient_started, dictation_done = asyncio.Event(), asyncio.Event()

    async def complete(self, messages, **kwargs):
        content = messages[1]["content"]
        if "Ambient" in content:
            ambient_started.set()
            await dictation_done.wait()
            return "Ambient sentence."
        await ambient_started.wait()
        dictation_done.set()
        return "Dictation sentence."

    monkeypatch.setattr(inference.LlamaClient, "complete", complete)
    source = streams.day_path(temp_root / "state/asr/whisper", clock.utc_now().date())
    streams.append(source, asr("sys", "Ambient sentence.", ident="ambient"))
    streams.append(source, asr("dic", "Dictation sentence.", ident="dictation"))
    await run(Speech(), once=True)
    results = streams.read_day(
        streams.day_path(temp_root / "state/text", clock.utc_now().date())
    )
    assert [r["input"] for r in results] == ["dictation", "ambient"]
    await run(Speech(), once=True)
    assert (
        len(
            streams.read_day(
                streams.day_path(temp_root / "state/text", clock.utc_now().date())
            )
        )
        == 2
    )


@pytest.mark.looptime(False)
async def test_recorded_llama_pair(temp_root):
    setup_audio(temp_root)
    pair = json.loads(
        (
            Path(inference.__file__).parent / "testdata/llama-cleanup-dictation.json"
        ).read_text()
    )
    server = inference.ReplayServer([pair])
    try:
        path = temp_root / "config/config.json"
        conf = json.loads(path.read_text())
        conf["common"]["inference"]["llama_url"] = server.url + inference.LLAMA_PATH
        path.write_text(json.dumps(conf))
        source = (
            pair["request"]["body"]["messages"][1]["content"]
            .removeprefix("<transcript>")
            .removesuffix("</transcript>")
        )
        result = await cleanup(asr("dic", source), Speech(), Host("llama"), once=True)
        assert result.outcome == "ok" and result.text
        body = json.loads(server.requests[0]["body"])
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
    finally:
        server.close()


@pytest.mark.parametrize("channel", ["sys", "dic"])
@pytest.mark.parametrize("local", [True, False])
async def test_battery_pending_cleanup(temp_root, monkeypatch, channel, local):
    from odsod_daemon.components.cleanup.worker import lane
    from odsod_daemon.components.transcription.host import HostUnavailable
    from odsod_daemon.lib import power

    setup_audio(temp_root)
    path = temp_root / "config/config.json"
    conf = json.loads(path.read_text())
    if not local:
        conf["common"]["inference"]["llama_url"] = (
            "http://100.64.0.1:8179/v1/chat/completions"
        )
    path.write_text(json.dumps(conf))
    monkeypatch.setattr(power, "on_mains", lambda: False)
    calls = []

    async def complete(*args, **kwargs):
        calls.append(True)
        return asr()["text"]

    monkeypatch.setattr(inference.LlamaClient, "complete", complete)
    streams.append(
        streams.day_path(temp_root / "state/asr/whisper", clock.utc_now().date()),
        asr(channel),
    )
    began = clock.monotonic()
    if local:
        with pytest.raises(HostUnavailable):
            await lane(Speech(), channel == "dic", once=True)
        assert clock.monotonic() - began == pytest.approx(60)
        assert not calls
        assert not list((temp_root / "state/text").glob("*.jsonl"))
    else:
        await lane(Speech(), channel == "dic", once=True)
        assert calls == [True]


def test_messages_pin_the_whisper_language():
    english = prompt.messages("Clean.", "That's it for me.", "en")[0]["content"]
    assert english.endswith(
        "The transcript is in English. Reply in English. Never translate."
    )
    swedish = prompt.messages("Clean.", "Och röntgen.", "sv")[0]["content"]
    assert "Reply in Swedish." in swedish
    assert prompt.messages("Clean.", "Hm.", "und")[0]["content"] == "Clean."
