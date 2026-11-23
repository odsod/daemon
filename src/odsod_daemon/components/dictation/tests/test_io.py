import asyncio
import json
import os

import pytest

import odsod_daemon.components.keys.contract as contract
from odsod_daemon.components.capture.contract import CAPTURE_APP_NAME
from odsod_daemon.components.dictation import delivery, mute, pactl
from odsod_daemon.components.dictation.keys_client import KeysClient
from odsod_daemon.components.dictation.tests.fakes import Keys
from odsod_daemon.lib import documents


@pytest.mark.looptime(False)
async def test_mute_selection_record_and_reused_id(desktop, temp_root, monkeypatch):
    (desktop / "sources.json").write_text(
        json.dumps(
            [{"index": 1, "monitor_of_sink": None}, {"index": 2, "monitor_of_sink": 0}]
        )
    )
    outputs = [
        {
            "index": i,
            "source": 2 if i == 4 else 1,
            "mute": i == 3,
            "properties": {"application.name": CAPTURE_APP_NAME if i == 2 else str(i)},
        }
        for i in range(1, 6)
    ]
    file = desktop / "source-outputs.json"
    file.write_text(json.dumps(outputs))
    path = temp_root / "run/muted.json"
    original = pactl.set_mute

    async def checked(stream_id, value):
        if value:
            assert {s["id"] for s in documents.read_json(path)["streams"]} == {"1", "5"}
        await original(stream_id, value)

    monkeypatch.setattr(pactl, "set_mute", checked)
    # Python fake startup costs are outside the real pactl latency budget.
    monkeypatch.setattr(mute, "MUTE_TIMEOUT", 2)
    manager = mute.Mute(path)
    assert await manager.start()
    current = json.loads(file.read_text())
    assert [s["mute"] for s in current] == [True, False, True, False, True]
    current[0]["properties"]["application.name"] = "reused"
    file.write_text(json.dumps(current[:-1]))  # stream 5 ended
    await manager.stop()
    assert json.loads(file.read_text())[0]["mute"]  # reused ID is untouched
    assert mute.read(path).streams == []


@pytest.mark.looptime(False)
@pytest.mark.parametrize("success", [True, False])
async def test_clipboard_round_trip(desktop, success):
    originals = [
        delivery.Selection("image/png", b"png\x00"),
        delivery.Selection(delivery.TEXT, b"old"),
    ]
    for primary, original in zip((False, True), originals, strict=True):
        await delivery.copy(primary, original)

    async def request():
        assert await delivery.save(False) == delivery.Selection(delivery.TEXT, b"hello")
        return success

    assert await delivery.paste("hello", request, 0) == success
    for primary, original in zip((False, True), originals, strict=True):
        assert await delivery.save(primary) == (
            original if success else delivery.Selection(delivery.TEXT, b"hello")
        )
    calls = (desktop / "calls.jsonl").read_text()
    assert "--sensitive" in calls
    assert ("paste failed" in calls) == (not success)


@pytest.mark.looptime(False)
async def test_clipboard_changed_during_paste(desktop):
    async def request():
        await delivery.copy(False, delivery.Selection(delivery.TEXT, b"owner copy"))
        return True

    assert await delivery.paste("hello", request, 0)
    assert await delivery.save(False) == delivery.Selection(
        delivery.TEXT, b"owner copy"
    )
    assert await delivery.save(True) == delivery.Selection(delivery.TEXT, b"")


@pytest.mark.looptime(False)
async def test_keys_codec_and_reply(tmp_path):
    fake = Keys()
    path = tmp_path / "keys.sock"
    async with await fake.serve(path):
        client = await KeysClient.connect(str(path))
        reader = asyncio.create_task(client.read())
        try:
            await fake.connected.wait()
            await fake.send(contract.Start(time="2026-11-23T10:00:00.000Z"))
            assert isinstance(await client.events.get(), contract.Start)
            assert await client.paste()
            fake.reply = False
            assert not await client.paste()
        finally:
            await client.close()
            await reader


async def test_restore_delay_and_oversize(monkeypatch):
    from odsod_daemon.lib import clock

    current = {False: delivery.Selection("image/png", b"old"), True: None}
    copies = []

    async def save(primary):
        return current[primary]

    async def copy(primary, value):
        copies.append((primary, value, clock.monotonic()))
        current[primary] = value

    async def request():
        return True

    monkeypatch.setattr(delivery, "save", save)
    monkeypatch.setattr(delivery, "copy", copy)
    start = clock.monotonic()
    assert await delivery.paste("hello", request, 500)
    assert copies[-1] == (False, delivery.Selection("image/png", b"old"), start + 0.5)
    assert len(copies) == 3  # Oversize PRIMARY is not restored.


def test_last_pending_and_late(temp_root):
    from datetime import timedelta

    from odsod_daemon.components.dictation.last import newest
    from odsod_daemon.lib import clock, streams

    now = clock.utc_now()
    assert newest()["state"] == "none"
    streams.append(
        streams.day_path(temp_root / "state/utterances/dictation", now.date()),
        {"id": "dic-test", "release": clock.iso(now), "press": clock.iso(now)},
    )
    assert newest()["state"] == "pending"
    streams.append(
        streams.day_path(temp_root / "state/text", now.date()),
        {
            "input": "dic-test",
            "outcome": "ok",
            "text": "late words",
            "raw": True,
            "ts": clock.iso(now + timedelta(seconds=11)),
        },
    )
    assert newest()["late"]
    assert newest()["raw"]
    assert newest()["text"] == "late words"


async def test_empty_selection_exit_is_not_a_clipboard_failure(monkeypatch):
    async def empty(*args, **kwargs):
        raise OSError("No selection")

    monkeypatch.setattr(delivery, "command", empty)
    assert await delivery.save(False) == delivery.Selection(delivery.TEXT, b"")


@pytest.mark.looptime(False)
async def test_copy_returns_while_a_forked_child_holds_the_pipes(tmp_path, monkeypatch):
    # Real wl-copy forks a child that serves the selection and keeps its fds.
    script = tmp_path / "wl-copy"
    script.write_text("#!/bin/sh\ncat >/dev/null\nsleep 3 &\nexit 0\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    async with asyncio.timeout(1):
        await delivery.copy(False, delivery.Selection(delivery.TEXT, b"hello"))
        await delivery.copy(True, delivery.Selection(delivery.TEXT, b""))
