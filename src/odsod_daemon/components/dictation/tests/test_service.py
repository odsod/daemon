import asyncio
import json
import subprocess

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.dictation import delivery, service
from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.components.dictation.contract import DictationUtterance
from odsod_daemon.lib import clock, documents, streams


@pytest.fixture
def session(temp_root, monkeypatch):
    session = service.Session(DictationConfig(), units=service.systemd.FakeUnitStates())
    effects = []

    async def mute_start():
        effects.append("mute")
        return False  # Failed mute must leave dictation usable.

    async def mute_stop():
        effects.append("unmute")

    async def coverage(*args, **kwargs):
        effects.append("cover")

    async def text(*args):
        await clock.sleep(0.01)
        return {"outcome": "ok", "text": "hello"}

    monkeypatch.setattr(session.mute, "start", mute_start)
    monkeypatch.setattr(session.mute, "stop", mute_stop)
    monkeypatch.setattr(service.audio, "wait_until", coverage)
    monkeypatch.setattr(service, "text_for", text)
    return session, effects


async def test_hold_order_and_cancel(session, monkeypatch):
    session, effects = session
    await session.startup()
    session.loop.event("connected")
    original_status = session.status
    original_append = streams.append

    def status():
        effects.append("idle" if session.idle.is_set() else "dictating")
        original_status()

    def append(*args):
        effects.append("append")
        original_append(*args)

    monkeypatch.setattr(session, "status", status)
    monkeypatch.setattr(streams, "append", append)
    now = clock.wall()
    effects.clear()
    await session.actions("start", now)
    assert effects == ["mute", "dictating"]
    state = documents.read_json(session.roots.run / "status.json")
    assert state["audio_start"] == service.stamp(now - 0.3)
    await session.actions("stop", now + 1)
    assert effects == ["mute", "dictating", "unmute", "cover", "append", "idle"]
    hold, timing, waiter = await session.queue.get()
    assert hold.start == service.stamp(now - 0.3)
    assert hold.end == service.stamp(now + 1.15)
    assert (await waiter)["text"] == "hello"
    assert "text" in timing
    effects.clear()
    await session.actions("start", now + 2)
    await session.actions("cancel", now + 3)
    assert effects == ["mute", "dictating", "unmute", "idle"]
    assert session.queue.empty()
    health = documents.read_json(session.roots.run / "health/session.json")
    assert "mute-failed" in {fault["code"] for fault in health["faults"]}


async def test_delivery_waits_for_new_hold(session, monkeypatch):
    session, _ = session
    pasted = []

    async def paste(text, request, delay):
        pasted.append(text)
        return True

    monkeypatch.setattr(delivery, "paste", paste)
    session.loop.event("connected")
    now = clock.wall()
    await session.actions("start", now)
    await session.actions("stop", now + 0.1)
    await session.actions("start", now + 0.2)
    job = asyncio.create_task(session.deliver_one(*await session.queue.get()))
    await clock.sleep(1)
    assert not pasted
    await session.actions("cancel", now + 0.3)
    await job
    assert pasted == ["hello"]


@pytest.mark.parametrize("outcome,text", [("empty", ""), ("ok", ""), ("failed", "")])
async def test_empty_and_failed_never_touch_clipboard(
    session, monkeypatch, outcome, text
):
    session, _ = session
    notices = []

    async def result(*args):
        return {"outcome": outcome, "text": text}

    async def notice(message):
        notices.append(message)

    async def forbidden(*args):
        raise AssertionError("clipboard touched")

    monkeypatch.setattr(service, "text_for", result)
    monkeypatch.setattr(service.notify, "send", notice)
    monkeypatch.setattr(delivery, "paste", forbidden)
    session.loop.event("connected")
    await session.actions("start", clock.wall())
    await session.actions("stop", clock.wall())
    await session.deliver_one(*await session.queue.get())
    assert notices == (["dictation failed"] if outcome == "failed" else [])


@pytest.mark.looptime(False)
async def test_text_timeout_and_late_result(temp_root):
    now = clock.utc_now()
    hold = DictationUtterance(
        ts=clock.iso(),
        id="dic-test",
        start=clock.iso(),
        end=clock.iso(),
        press=clock.iso(),
        release=clock.iso(),
        muted=0,
    )
    with pytest.raises(TimeoutError):
        await service.text_for(temp_root / "state", hold, clock.wall() + 0.02)
    streams.append(
        streams.day_path(temp_root / "state/text", now.date()),
        {"input": hold.id, "outcome": "ok", "text": "late"},
    )
    with pytest.raises(TimeoutError):
        await service.text_for(temp_root / "state", hold, clock.wall() - 1)


def test_last_cli(temp_root):
    (temp_root / "config/config.json").write_text("{}")
    now = clock.iso()
    streams.append(
        streams.day_path(
            temp_root / "state/utterances/dictation", clock.utc_now().date()
        ),
        {"id": "dic-test", "press": now, "release": now},
    )
    result = CliRunner().invoke(app, ["dictation", "last", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["state"] == "pending"


def test_unmute_import_is_light():
    result = subprocess.run(
        [
            "timeout",
            "10",
            "uv",
            "run",
            "python",
            "-c",
            "import sys; import odsod_daemon.components.unmute_stale.cli; "
            "assert not any(m in sys.modules for m in "
            "('onnxruntime','numpy','PySide6','odsod_daemon.components.dictation.service'))",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "capture,reachable,mains,expected",
    [
        (False, True, True, "paused"),
        (True, False, True, "no-inference"),
        (True, True, False, "no-inference"),
        (True, True, True, "no-socket"),
    ],
)
async def test_gate_and_missing_socket(
    temp_root, monkeypatch, capture, reachable, mains, expected
):
    documents.write_json(
        temp_root / "config/config.json",
        {
            "common": {
                "inference": {
                    "whisper_url": "http://127.0.0.1:1/asr",
                    "llama_url": "http://127.0.0.1:1/chat",
                }
            }
        },
    )
    units = service.systemd.FakeUnitStates()
    units.set(
        service.systemd.UnitState(
            "odsod-daemon-capture.service",
            "user",
            "active" if capture else "inactive",
            "",
            "",
            0,
        )
    )
    # A socket path that exists but refuses connections must fault within 10 s.
    path = temp_root / "refused.sock"
    path.touch()
    session = service.Session(DictationConfig(), units=units, socket_path=str(path))

    async def probe(*args, **kwargs):
        return reachable

    async def connect(*args):
        raise ConnectionRefusedError

    monkeypatch.setattr(service.inference, "reachable", probe)
    monkeypatch.setattr(service.power, "on_mains", lambda: mains)
    monkeypatch.setattr(service.KeysClient, "connect", connect)
    task = asyncio.create_task(session.connections())
    try:
        await clock.sleep(10.01)
        assert session.keys == expected
        health = documents.read_json(temp_root / "run/health/session.json")
        assert ("keys-socket-missing" in {f["code"] for f in health["faults"]}) == (
            expected == "no-socket"
        )
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
