"""Recorded llama replies and map-reduce request contracts."""

import json
from pathlib import Path

import pytest

from odsod_daemon.components.interactions.config import InteractionsConfig
from odsod_daemon.components.interactions.summarize import Summarizer
from odsod_daemon.lib import inference, paths

DATA = Path(inference.__file__).parent / "testdata"


@pytest.mark.parametrize("limit,calls", [(37000, 1), (20, 3)])
@pytest.mark.looptime(False)
async def test_recorded_summary(temp_root, limit, calls):
    pair = json.loads((DATA / "llama-summary.json").read_text())
    server = inference.ReplayServer([pair] * calls)
    try:
        runner = Summarizer(
            InteractionsConfig(chunk_chars=limit),
            paths.roots(),
            server.url + inference.LLAMA_PATH,
        )
        result, setup = await runner("[10:00:00] A: Hej\n[10:00:10] B: Ja")
        assert result.title == "Postgres Migration and CDC Lag"
        assert len(server.requests) == calls
        for request in server.requests:
            body = json.loads(request["body"])
            assert body["response_format"] == pair["request"]["body"]["response_format"]
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert setup.startswith("default:")
        if calls == 3:
            assert (
                "Combine"
                in json.loads(server.requests[-1]["body"])["messages"][0]["content"]
            )
    finally:
        server.close()


@pytest.mark.looptime(False)
async def test_error_reply(temp_root):
    pair = json.loads((DATA / "llama-bad-request.json").read_text())
    server = inference.ReplayServer([pair])
    try:
        import httpx

        runner = Summarizer(
            InteractionsConfig(), paths.roots(), server.url + inference.LLAMA_PATH
        )
        with pytest.raises(httpx.HTTPStatusError):
            await runner("Transcript")
    finally:
        server.close()


def test_prompt_overrides_and_setup(temp_root):
    roots = paths.roots()
    prompts = roots.config / "prompts"
    prompts.mkdir()
    (prompts / "interactions-summarize.md").write_text(
        "{{ owner_name }} {{ glossary | join(',') }}"
    )
    (roots.config / "glossary.yaml").write_text("- term: First\n- term: Last\n")
    one = Summarizer(
        InteractionsConfig(owner_name="Oscar"), roots, "http://localhost:8179"
    )
    assert one.prompts["summarize"] == "Oscar First,Last"
    two = Summarizer(
        InteractionsConfig(owner_name="Alice"), roots, "http://localhost:8179"
    )
    assert one.setup != two.setup
