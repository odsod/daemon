"""Live rehearsal: the dictation loop in front of the real speech servers.

Needs the owner's config in ``~/.config/odsod-daemon``, a reachable
whisper-server and llama-server, and is skipped otherwise. Run with
``uv run pytest -m live -s tests/test_dictation_live.py``.
"""

import asyncio
import base64
import json
import os
import re
import shutil
import wave
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from odsod_daemon.components import cleanup, transcription
from odsod_daemon.components.dictation import delivery
from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.components.dictation.service import Session
from odsod_daemon.components.dictation.tests.fakes import Keys
from odsod_daemon.components.keys.contract import Start, Stop
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.lib import (
    audio,
    clock,
    config,
    documents,
    inference,
    streams,
    systemd,
)

pytestmark = pytest.mark.live

BIN = Path(__file__).parents[1] / "src/odsod_daemon/components/dictation/tests/bin"
FIXTURES = Path(__file__).parent / "testdata/audio"
OWNER = Path.home() / ".config/odsod-daemon"


def urls():
    try:
        raw = json.loads((OWNER / "config.json").read_text())
        common = raw["common"]["inference"]
        return common["whisper_url"], common["llama_url"]
    except OSError, ValueError, KeyError, TypeError:
        return None


URLS = urls()
if URLS is None:
    pytest.skip(f"no inference config in {OWNER}", allow_module_level=True)
if not all(asyncio.run(inference.reachable(url, timeout_s=1)) for url in URLS):
    pytest.skip(
        f"whisper or llama server not reachable: {URLS}", allow_module_level=True
    )


def copy_config(root, **overrides):
    """The owner's config in the temp root, then the test's speech overrides."""
    target = root / "config"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(OWNER / "config.json", target / "config.json")
    glossary = OWNER / "glossary.yaml"
    if glossary.exists():
        # copy follows the symlink into the brain vault.
        shutil.copy(glossary, target / "glossary.yaml")
    prompts = OWNER / "prompts"
    if prompts.is_dir():
        shutil.copytree(prompts, target / "prompts", dirs_exist_ok=True)
    raw = json.loads((target / "config.json").read_text())
    raw["speech"] = {**raw.get("speech", {}), **overrides}
    (target / "config.json").write_text(json.dumps(raw, indent=2))
    return config.section("speech", Speech)


def pcm(name):
    with wave.open(str(FIXTURES / name)) as handle:
        assert handle.getframerate() == audio.SAMPLE_RATE
        assert handle.getnchannels() == 1
        return handle.readframes(handle.getnframes())


def place(root, start, data):
    """Write samples into the mic hour buffer from a wall-clock time."""
    cursor = start
    while data:
        end = audio.hour_end(cursor)
        count = min(len(data), round((end - cursor).total_seconds() * 16000) * 2)
        file = audio.hour_file(root / "state", "mic", cursor)
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("r+b" if file.exists() else "w+b") as handle:
            offset = (
                round((cursor - audio.hour_start(cursor)).total_seconds() * 16000) * 2
            )
            handle.seek(offset)
            handle.write(data[:count])
        cursor += timedelta(seconds=count / 32000)
        data = data[count:]


def desktop(root):
    """One meeting stream the fake pactl can mute and the fake clipboard."""
    path = root / "desktop"
    path.mkdir()
    documents.write_json(path / "sources.json", [{"index": 1, "monitor_of_sink": None}])
    documents.write_json(
        path / "source-outputs.json",
        [
            {
                "index": 1,
                "source": 1,
                "mute": False,
                "properties": {"application.name": "meeting"},
            }
        ],
    )
    return path


def active_capture():
    units = systemd.FakeUnitStates()
    units.set(
        systemd.UnitState(
            "odsod-daemon-capture.service", "user", "active", "running", "success", 0
        )
    )
    return units


async def until(check, seconds=30, poll_s=0.01):
    async with asyncio.timeout(seconds):
        while not check():
            await asyncio.sleep(poll_s)


def records(root, stream):
    return [
        record
        for path in sorted((root / "state" / stream).glob("*.jsonl"))
        for record in streams.read_day(path)
    ]


async def rehearse(root, monkeypatch, speech):
    """Session, speech workers and the fake keys socket on one temp root."""
    monkeypatch.setattr("odsod_daemon.lib.power.on_mains", lambda: True)
    monkeypatch.setenv("PATH", f"{BIN}:{os.environ['PATH']}")
    fake = Keys()
    stamps = []

    def clipboard():
        path = root / "desktop/clipboard.json"
        value = json.loads(path.read_text()) if path.exists() else {"data": ""}
        return base64.b64decode(value["data"])

    fake.on_paste = lambda: (stamps.append(clock.monotonic()), clipboard())[1]
    socket = root / "keys.sock"
    server = await fake.serve(socket)
    session = Session(
        DictationConfig(text_timeout_s=10, restore_delay_ms=10),
        socket_path=str(socket),
        units=active_capture(),
    )
    tasks = [
        asyncio.create_task(session.run()),
        asyncio.create_task(transcription.run(speech)),
        asyncio.create_task(cleanup.run(speech)),
    ]
    await until(fake.connected.is_set, seconds=10)
    show = SimpleNamespace(
        root=root,
        desktop=root / "desktop",
        fake=fake,
        session=session,
        stamps=stamps,
        tasks=tasks,
    )

    async def stop():
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.close()
        await server.wait_closed()

    show.stop = stop
    return show


async def hold(show, samples):
    """Press, speak the samples in real time, then release."""
    press = clock.utc_now()
    place(
        show.root,
        press - timedelta(seconds=0.3),
        samples + bytes(audio.BYTES_PER_SECOND),  # One second of tail silence.
    )
    show.held_ms = round(len(samples) / 32000 * 1000)
    await show.fake.send(Start(time=clock.iso(press)))
    await asyncio.sleep(len(samples) / 32000 + 0.05)
    show.released = clock.monotonic()
    await show.fake.send(Stop(time=clock.iso()))


def pasted(show):
    return show.fake.pastes[0] if show.fake.pastes else None


async def report(show, case):
    """Wait for the hold to finish and print one timing line per case."""
    if pasted(show) is None:
        await until_session_done(show)
        print(f"dictation-live {case} stop_to_paste_ms=none")
        return None
    hold_id = await until_session_done(show)
    ms = round((show.stamps[0] - show.released) * 1000)
    asr = next(r for r in records(show.root, "asr/whisper") if r["input"] == hold_id)
    text = next(r for r in records(show.root, "text") if r["input"] == hold_id)
    print(
        f"dictation-live {case} stop_to_paste_ms={ms}"
        f" asr_ms={asr['ms']} cleanup_ms={text['ms']} raw={text.get('raw', False)}"
        f" held_ms={show.held_ms}"
    )
    return ms


@pytest.mark.looptime(False)
async def test_live_english_dictation_pastes_clean_text_in_two_seconds(
    temp_root, monkeypatch
):
    """PRD dictation AC-3 with the real servers and the owner's glossary."""
    speech = copy_config(temp_root)
    desktop(temp_root)
    show = await rehearse(temp_root, monkeypatch, speech)
    try:
        await hold(show, pcm("en-chinese-feet.wav"))
        await until(lambda: pasted(show) is not None, seconds=20)
        spoken = pasted(show)
        assert spoken is not None
        text = spoken.decode()
        print(f"dictation-live en-chinese-feet text={text!r}")
        expected = set(words((FIXTURES / "en-chinese-feet.txt").read_text()))
        assert len(expected) >= 10
        share = len(expected & words(text)) / len(expected)
        print(f"dictation-live en-chinese-feet shared_words={share:.2f}")
        assert share >= 0.6, text
        ms = await report(show, "en-chinese-feet")
        assert ms is not None
        assert ms <= 2000, f"{ms} ms"
    finally:
        await show.stop()


@pytest.mark.looptime(False)
async def test_live_silence_pastes_nothing(temp_root, monkeypatch):
    """PRD dictation AC-7: a hold with no speech never touches the clipboard."""
    speech = copy_config(temp_root)
    desktop(temp_root)
    show = await rehearse(temp_root, monkeypatch, speech)
    original = delivery.Selection(delivery.TEXT, b"owner text")
    await delivery.copy(False, original)
    try:
        await hold(show, pcm("silence.wav"))
        assert await report(show, "silence") is None
        assert not show.fake.pastes
        assert await delivery.save(False) == original
    finally:
        await show.stop()


@pytest.mark.looptime(False)
async def test_live_second_latency_sample(temp_root, monkeypatch):
    """PRD dictation AC-3 on a second reading, longer than the first."""
    speech = copy_config(temp_root)
    desktop(temp_root)
    show = await rehearse(temp_root, monkeypatch, speech)
    try:
        await hold(show, pcm("en-study-in-scarlet.wav"))
        await until(lambda: pasted(show) is not None, seconds=20)
        spoken = pasted(show)
        assert spoken is not None
        print(f"dictation-live en-study-in-scarlet text={spoken.decode()!r}")
        ms = await report(show, "en-study-in-scarlet")
        assert ms is not None
        assert ms <= 2000, f"{ms} ms"
    finally:
        await show.stop()


@pytest.mark.looptime(False)
async def test_live_slow_cleanup_pastes_raw_text(temp_root, monkeypatch):
    """PRD dictation AC-22: a cleanup that misses its limit pastes raw ASR."""
    speech = copy_config(temp_root, dictation={"cleanup_timeout_ms": 1})
    desktop(temp_root)
    show = await rehearse(temp_root, monkeypatch, speech)
    try:
        await hold(show, pcm("en-chinese-feet.wav"))
        await until(lambda: pasted(show) is not None, seconds=20)
        hold_id = records(temp_root, "utterances/dictation")[-1]["id"]
        text = next(r for r in records(temp_root, "text") if r["input"] == hold_id)
        asr = next(
            r for r in records(temp_root, "asr/whisper") if r["input"] == hold_id
        )
        assert text["raw"] is True and text["raw_reason"] == "timeout", text
        assert pasted(show) == text["text"].encode() == asr["text"].encode()
        ms = await report(show, "slow-cleanup")
        assert ms is not None
        assert ms <= 2000, f"{ms} ms"
    finally:
        await show.stop()


async def until_session_done(show):
    """Wait for the session to finish the hold and return the utterance ID."""
    await until(
        lambda: (
            show.session.queue.empty()
            and not show.session.waiters
            and show.session.idle.is_set()
            and records(show.root, "text")
        ),
        seconds=25,
    )
    return records(show.root, "utterances/dictation")[-1]["id"]


def words(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))
