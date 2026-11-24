"""Dictation PRD criteria that need the session, the fakes and real time."""

import asyncio
import json
from datetime import timedelta

import pytest

from odsod_daemon.components.dictation import delivery, pactl, service
from odsod_daemon.components.dictation.config import POSTROLL, DictationConfig
from odsod_daemon.components.dictation.service import Session
from odsod_daemon.components.dictation.tests.fakes import Keys
from odsod_daemon.components.keys.contract import Start, Stop
from odsod_daemon.lib import audio, clock, documents, streams, systemd


def status_mode(root):
    path = root / "run/status.json"
    return documents.read_json(path)["mode"] if path.exists() else None


def calls(desktop):
    path = desktop / "calls.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def meeting(desktop):
    """One non-monitor source and one meeting stream that mute can silence."""
    documents.write_json(
        desktop / "sources.json", [{"index": 1, "monitor_of_sink": None}]
    )
    documents.write_json(
        desktop / "source-outputs.json",
        [
            {
                "index": 1,
                "source": 1,
                "mute": False,
                "properties": {"application.name": "meeting"},
            }
        ],
    )


def active_capture():
    units = systemd.FakeUnitStates()
    units.set(
        systemd.UnitState(
            "odsod-daemon-capture.service", "user", "active", "running", "success", 0
        )
    )
    return units


def cover(state_root, moment):
    """Extend the mic hour buffer with silence through ``moment``."""
    file = audio.hour_file(state_root, "mic", moment)
    file.parent.mkdir(parents=True, exist_ok=True)
    offset = (
        round((moment - audio.hour_start(moment)).total_seconds() * audio.SAMPLE_RATE)
        * 2
    )
    with file.open("r+b" if file.exists() else "w+b") as handle:
        handle.seek(max(0, offset - 2))
        handle.write(bytes(2))


async def until(check, seconds=10, poll_s=0.001):
    async with asyncio.timeout(seconds):
        while not check():
            await asyncio.sleep(poll_s)


async def rehearse(desktop, temp_root, monkeypatch, settings, *, reply=True):
    """Serve the keys socket and start a session over the fake desktop."""
    meeting(desktop)
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
    monkeypatch.setattr(service.power, "on_mains", lambda: True)

    async def probe(*args, **kwargs):
        return True

    monkeypatch.setattr(service.inference, "reachable", probe)
    fake = Keys()
    fake.reply = reply
    stamps = []
    fake.on_paste = lambda: (stamps.append(clock.monotonic()), b"")[1]
    socket = temp_root / "keys.sock"
    server = await fake.serve(socket)
    session = Session(settings, socket_path=str(socket), units=active_capture())
    task = asyncio.create_task(session.run())
    await until(fake.connected.is_set)
    return fake, server, task, stamps


async def stop_rehearsal(server, task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    server.close()
    await server.wait_closed()


def hold_span():
    """Press and release times in the past, with room for the text wait."""
    press = clock.utc_now() - timedelta(seconds=1)
    return press, press + timedelta(seconds=0.5)


async def hold(fake, temp_root, press, release):
    cover(temp_root / "state", release + timedelta(seconds=POSTROLL))
    await fake.send(Start(time=clock.iso(press)))
    await until(lambda: status_mode(temp_root) == "dictating")
    await fake.send(Stop(time=clock.iso(release)))


@pytest.mark.timing
@pytest.mark.looptime(False)
async def test_dictating_status_within_200_ms_of_start(desktop, temp_root, monkeypatch):
    """PRD dictation AC-1.

    The real mute budget (150 ms) covers the fake pactl calls on this host.
    """
    fake, server, task, _ = await rehearse(
        desktop, temp_root, monkeypatch, DictationConfig(restore_delay_ms=10)
    )
    # The real pactl is a warm process; the Python fake pays a cold start once.
    await pactl.command("pactl", "--format=json", "list", "source-outputs")
    try:
        sent = clock.monotonic()
        await fake.send(Start(time=clock.iso()))
        await until(lambda: status_mode(temp_root) == "dictating", seconds=5)
        elapsed_ms = (clock.monotonic() - sent) * 1000
        print(f"start_to_dictating_ms={elapsed_ms:.0f}")
        assert elapsed_ms <= 200, f"{elapsed_ms:.0f} ms"
        # Mute comes first, so the tray never shows Dictating over a live mic.
        outputs = documents.read_json(desktop / "source-outputs.json")
        assert [stream["mute"] for stream in outputs] == [True]
    finally:
        await stop_rehearsal(server, task)


@pytest.mark.looptime(False)
async def test_no_text_within_wait_notifies_and_leaves_clipboard(
    desktop, temp_root, monkeypatch
):
    """PRD dictation AC-18.

    Nothing writes text/, so the wait ends and no paste is requested.
    """
    fake, server, task, _ = await rehearse(
        desktop,
        temp_root,
        monkeypatch,
        DictationConfig(text_timeout_s=0.3, restore_delay_ms=10),
    )
    original = delivery.Selection(delivery.TEXT, b"owner text")
    await delivery.copy(False, original)
    (desktop / "calls.jsonl").unlink()  # Setup writes are not dictation calls.
    try:
        press, release = hold_span()
        await hold(fake, temp_root, press, release)
        await until(
            lambda: any(call[0] == "notify-send" for call in calls(desktop)),
            seconds=5,
        )
        notices = [call for call in calls(desktop) if call[0] == "notify-send"]
        assert notices == [["notify-send", "Dictation", "dictation failed"]]
        assert not [call for call in calls(desktop) if call[0] == "wl-copy"]
        assert not fake.pastes
        assert await delivery.save(False) == original
    finally:
        await stop_rehearsal(server, task)


@pytest.mark.looptime(False)
async def test_paste_failed_keeps_text_and_notifies_within_one_second(
    desktop, temp_root, monkeypatch
):
    """PRD dictation AC-20.

    The fake keys answers paste-failed; the text stays on the clipboard.
    """
    fake, server, task, stamps = await rehearse(
        desktop,
        temp_root,
        monkeypatch,
        DictationConfig(text_timeout_s=10, restore_delay_ms=10),
        reply=False,
    )
    original = delivery.Selection("image/png", b"owner image\x00")
    await delivery.copy(False, original)
    (desktop / "calls.jsonl").unlink()  # Setup writes are not dictation calls.
    try:
        press, release = hold_span()
        await hold(fake, temp_root, press, release)
        await until(lambda: streams.read_day(utterance_day(temp_root)))
        record = streams.read_day(utterance_day(temp_root))[0]
        streams.append(
            text_day(temp_root),
            {"input": record["id"], "outcome": "ok", "text": "hello dictation"},
        )
        await until(lambda: stamps)
        await until(
            lambda: any(call[0] == "notify-send" for call in calls(desktop)),
            seconds=5,
        )
        elapsed_ms = (clock.monotonic() - stamps[0]) * 1000
        print(f"paste_failed_to_notice_ms={elapsed_ms:.0f}")
        assert elapsed_ms <= 1000, f"{elapsed_ms:.0f} ms"
        notices = [call for call in calls(desktop) if call[0] == "notify-send"]
        assert notices == [
            ["notify-send", "Dictation", "paste failed: the text is on the clipboard"]
        ]
        assert await delivery.save(False) == delivery.Selection(
            delivery.TEXT, b"hello dictation"
        )
    finally:
        await stop_rehearsal(server, task)


def utterance_day(root):
    return streams.day_path(root / "state/utterances/dictation", clock.utc_now().date())


def text_day(root):
    return streams.day_path(root / "state/text", clock.utc_now().date())
