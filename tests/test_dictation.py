"""Dictation across real file seams, with no input or desktop devices."""

import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import wave
from datetime import timedelta
from pathlib import Path

import pytest

from odsod_daemon.components import cleanup, transcription
from odsod_daemon.components.dictation import delivery
from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.components.dictation.service import Session
from odsod_daemon.components.dictation.tests.fakes import Keys
from odsod_daemon.components.keys.contract import Cancel, Start, Stop
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.lib import audio, clock, documents, inference, streams, systemd

BIN = Path(__file__).parents[1] / "src/odsod_daemon/components/dictation/tests/bin"
DATA = Path(inference.__file__).parent / "testdata"


def pair(name):
    return json.loads((DATA / f"{name}.json").read_text())


def read(root, directory):
    return [
        r
        for p in sorted((root / "state" / directory).glob("*.jsonl"))
        for r in streams.read_day(p)
    ]


def units():
    source = systemd.FakeUnitStates()
    source.set(
        systemd.UnitState(
            "odsod-daemon-capture.service", "user", "active", "running", "success", 0
        )
    )
    return source


def configure(root, whisper, llama):
    documents.write_json(
        root / "config/config.json",
        {
            "common": {
                "inference": {
                    "whisper_url": whisper.url + inference.WHISPER_PATH,
                    "llama_url": llama.url + inference.LLAMA_PATH,
                }
            }
        },
    )


async def until(check, seconds=8):
    async with clock.timeout(seconds):
        while not check():
            await clock.sleep(0.01)


class Capture:
    def __init__(self, root, start):
        self.state = root / "state"
        self.start = start
        self.cursor = start

    def write(self, pcm):
        while pcm:
            end = audio.hour_end(self.cursor)
            count = min(
                len(pcm), round((end - self.cursor).total_seconds() * 16000) * 2
            )
            file = audio.hour_file(self.state, "mic", self.cursor)
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("r+b" if file.exists() else "w+b") as handle:
                handle.seek(
                    round(
                        (self.cursor - audio.hour_start(self.cursor)).total_seconds()
                        * 16000
                    )
                    * 2
                )
                handle.write(pcm[:count])
            self.cursor += timedelta(seconds=count / 32000)
            pcm = pcm[count:]


@pytest.fixture
def desktop(temp_root, monkeypatch):
    monkeypatch.setenv("PATH", f"{BIN}:{os.environ['PATH']}")
    path = temp_root / "desktop"
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


@pytest.mark.looptime(False)
@pytest.mark.parametrize(
    "case", ["ok", "mute-failed", "paste-failed", "cancel", "silence"]
)
async def test_dictation_speech_and_paste(
    temp_root, desktop, monkeypatch, caplog, case
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("odsod_daemon.lib.power.on_mains", lambda: True)
    wp = pair("whisper-dictation-verbose")
    expected = " ".join(wp["response"]["json"]["text"].split())
    lp = pair("llama-cleanup-dictation")
    lp["response"]["json"]["choices"][0]["message"]["content"] = expected
    whisper = inference.ReplayServer([wp for _ in range(4)])
    llama = inference.ReplayServer([lp for _ in range(4)])
    configure(temp_root, whisper, llama)
    # Executable Python fakes test order, not the pactl latency budget.
    monkeypatch.setattr("odsod_daemon.components.dictation.mute.MUTE_TIMEOUT", 2)
    fake = Keys()
    fake.reply = case != "paste-failed"
    fake.on_paste = lambda: base64.b64decode(
        documents.read_json(desktop / "clipboard.json")["data"]
    )
    socket = temp_root / "keys.sock"
    tasks = []
    keys_server = await fake.serve(socket)
    try:
        session = Session(
            DictationConfig(text_timeout_s=5, restore_delay_ms=10),
            socket_path=str(socket),
            units=units(),
        )
        original = delivery.Selection("image/png", b"original\x00")
        await delivery.copy(False, original)
        await delivery.copy(True, delivery.Selection(delivery.TEXT, b"primary"))
        if case == "mute-failed":
            (desktop / "pactl.fail").touch()
        tasks.append(asyncio.create_task(session.run()))
        await until(fake.connected.is_set)
        with wave.open(
            str(Path(__file__).parent / "testdata/audio/en-chinese-feet.wav")
        ) as handle:
            pcm = handle.readframes(handle.getnframes())
        if case == "silence":
            pcm = bytes(len(pcm))
        release = clock.utc_now()
        press = release - timedelta(seconds=len(pcm) / 32000)
        start = press - timedelta(seconds=0.3)
        capture = Capture(temp_root, start)
        recording = bytes(9600) + pcm + bytes(4800)
        middle = len(recording) // 4 * 2
        capture.write(recording[:middle])
        await fake.send(Start(time=clock.iso(press)))
        await until(
            lambda: (
                documents.read_json(temp_root / "run/status.json")["mode"]
                == "dictating"
            )
        )
        # Capture keeps writing while the meeting's fake stream is muted.
        capture.write(recording[middle:])
        if case == "mute-failed":
            (desktop / "pactl.fail").unlink()
        await fake.send(
            Cancel(time=clock.iso(release))
            if case == "cancel"
            else Stop(time=clock.iso(release))
        )
        await until(
            lambda: documents.read_json(temp_root / "run/status.json")["mode"] == "idle"
        )
        assert audio.cut(temp_root / "state", "mic", start, capture.cursor) == recording
        if case == "cancel":
            assert not read(temp_root, "utterances/dictation")
            assert not fake.pastes
            assert await delivery.save(False) == original
            return
        hold = read(temp_root, "utterances/dictation")[0]
        # Put ambient work behind the completed hold before speech starts.
        for i in range(2):
            streams.append(
                streams.day_path(temp_root / "state/utterances/ambient", start.date()),
                {
                    "id": f"amb-{i}",
                    "channel": "mic",
                    "start": hold["start"],
                    "end": hold["end"],
                },
            )
        speech = Speech()
        tasks.extend(
            [
                asyncio.create_task(transcription.run(speech)),
                asyncio.create_task(cleanup.run(speech)),
            ]
        )
        await until(
            lambda: any(r["input"] == hold["id"] for r in read(temp_root, "text"))
        )
        await until(lambda: session.queue.empty() and not session.waiters)
        await session.queue.join()
        assert read(temp_root, "asr/whisper")[0]["input"] == hold["id"]
        if case == "silence":
            assert not fake.pastes
            assert await delivery.save(False) == original
            return
        assert fake.pastes == [expected.encode()]
        assert await delivery.save(False) == (
            delivery.Selection(delivery.TEXT, expected.encode())
            if case == "paste-failed"
            else original
        )
        if case == "paste-failed":
            assert (
                "paste failed: the text is on the clipboard"
                in (desktop / "calls.jsonl").read_text()
            )
        if case == "mute-failed":
            assert "mute-failed" in {
                f["code"]
                for f in documents.read_json(temp_root / "run/health/session.json")[
                    "faults"
                ]
            }
        timings = [r.message for r in caplog.records if "dictation timing" in r.message]
        assert len(timings) == 1
        for field in ("release", "coverage", "append", "text", "paste"):
            assert field in timings[0]
        assert ("'pasted'" in timings[0]) == (case != "paste-failed")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        keys_server.close()
        await keys_server.wait_closed()
        whisper.close()
        llama.close()


@pytest.mark.looptime(False)
async def test_dictation_crash_cleanup_without_restart(temp_root, desktop):
    """PRD dictation AC-17, AC-26: a crash leaves no muted meeting and no open
    mic that the hold unmuted."""
    # The owner's hardware mute is on.
    (desktop / "default-source.txt").write_text("mic\n")
    documents.write_json(
        desktop / "sources.json",
        [{"index": 1, "name": "mic", "mute": True, "monitor_of_sink": None}],
    )
    server = inference.ReplayServer([])
    configure(temp_root, server, server)
    fake = Keys()
    socket = temp_root / "keys.sock"
    process = None
    keys_server = await fake.serve(socket)
    try:
        code = (
            "import asyncio,sys; "
            "import odsod_daemon.components.dictation.mute as mute; "
            "mute.MUTE_TIMEOUT=2; "
            "from odsod_daemon.components.dictation.service import Session; "
            "from odsod_daemon.components.dictation.config import DictationConfig; "
            "from odsod_daemon.lib.systemd import FakeUnitStates,UnitState; "
            "units=FakeUnitStates(); "
            "units.set(UnitState('odsod-daemon-capture.service',"
            "'user','active','','',0)); "
            "asyncio.run(Session(DictationConfig(),socket_path=sys.argv[1],units=units).run())"
        )
        process = subprocess.Popen(
            ["timeout", "20", "uv", "run", "python", "-c", code, str(socket)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        await until(fake.connected.is_set)
        await fake.send(Start(time=clock.iso()))
        await until(
            lambda: (
                documents.read_json(temp_root / "run/status.json")["mode"]
                == "dictating"
            )
        )
        assert documents.read_json(desktop / "source-outputs.json")[0]["mute"]
        assert not documents.read_json(desktop / "sources.json")[0]["mute"]
        record = (temp_root / "run/muted.json").read_bytes()
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        result = await asyncio.to_thread(
            subprocess.run,
            ["timeout", "10", "uv", "run", "odsodctl", "unmute-stale"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert not documents.read_json(desktop / "source-outputs.json")[0]["mute"]
        assert documents.read_json(desktop / "sources.json")[0]["mute"]
        assert (temp_root / "run/muted.json").read_bytes() == record
        await until(lambda: fake.writer is None)
        # A later start clears the record and reports the recovered mutes.
        result = await asyncio.to_thread(
            subprocess.run,
            ["timeout", "10", "uv", "run", "odsodctl", "run", "session", "--once"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert documents.read_json(temp_root / "run/muted.json")["streams"] == []
        assert "stale-mutes-cleared" in {
            f["code"]
            for f in documents.read_json(temp_root / "run/health/session.json")[
                "faults"
            ]
        }
    finally:
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        keys_server.close()
        await keys_server.wait_closed()
        server.close()
