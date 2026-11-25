"""Speech through file seams and subprocesses, with fake capture and inference."""

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import threading
import wave
from pathlib import Path

import pytest

from odsod_daemon.lib import audio, clock, inference, streams

AUDIO = Path(__file__).parent / "testdata/audio"
DATA = Path(inference.__file__).parent / "testdata"


class FakeCapture:
    """Write fixture samples to the same hourly buffer seam as capture."""

    def __init__(self, root: Path):
        self.root = root
        self.start = audio.hour_start(clock.utc_now())

    def write(self):
        with wave.open(str(AUDIO / "sv-udhr-article1.wav")) as handle:
            pcm = handle.readframes(handle.getnframes()) + bytes(32000)
        path = audio.hour_file(self.root / "state", "sys", self.start)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pcm)


def read(root: Path, stream: str) -> list[dict]:
    return [
        r
        for path in sorted((root / "state" / stream).glob("*.jsonl"))
        for r in streams.read_day(path)
    ]


def pair(name, *, delay_ms=0):
    value = json.loads((DATA / f"{name}.json").read_text())
    value["response"]["delay_ms"] = delay_ms
    return value


def configure(root, whisper, llama):
    (root / "config/config.json").write_text(
        json.dumps(
            {
                "common": {
                    "inference": {
                        "whisper_url": whisper.url + inference.WHISPER_PATH,
                        "llama_url": llama.url + inference.LLAMA_PATH,
                    }
                },
                "speech": {"segmentation": {"min_silence_ms": 800}},
            }
        )
    )


def drain(target):
    result = subprocess.run(
        ["timeout", "20", "uv", "run", "odsodctl", "run", target, "--once"],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.looptime(False)
@pytest.mark.parametrize("boundary", ["utterances/ambient", "asr/whisper", "text"])
async def test_speech_pipeline_kill_and_restart(temp_root, boundary):
    whisper = inference.ReplayServer(
        [pair("whisper-sv-verbose", delay_ms=100) for _ in range(20)]
    )
    llama = inference.ReplayServer(
        [pair("llama-cleanup-ambient", delay_ms=100) for _ in range(20)]
    )
    process = None
    try:
        configure(temp_root, whisper, llama)
        FakeCapture(temp_root).write()
        process = subprocess.Popen(
            ["timeout", "20", "uv", "run", "odsodctl", "run", "pipeline"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = clock.monotonic() + 12
        while not read(temp_root, boundary):
            assert process.poll() is None, process.communicate()[1].decode()
            assert clock.monotonic() < deadline, f"pipeline did not reach {boundary}"
            await clock.sleep(0.005)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        drain("pipeline")
        utterances = read(temp_root, "utterances/ambient")
        asr = read(temp_root, "asr/whisper")
        text = read(temp_root, "text")
        ids = {r["id"] for r in utterances}
        assert ids
        assert len(utterances) == len(ids)
        assert len(asr) == len(text) == len(ids)
        assert {r["input"] for r in asr} == {r["input"] for r in text} == ids
        assert all(r["outcome"] == "ok" and r["language"] == "sv" for r in text)
        # A second full drain proves that all three pending sets are empty.
        drain("pipeline")
        assert read(temp_root, "text") == text
        assert read(temp_root, "utterances/ambient") == utterances
        # Compare with uninterrupted segmentation to detect lost speech after a kill.
        for directory in ("utterances/ambient", "coverage"):
            for file in (temp_root / "state" / directory).glob("*.jsonl"):
                file.unlink()
        drain("segmentation")
        uninterrupted = read(temp_root, "utterances/ambient")
        assert len(uninterrupted) == len(utterances)
        for expected, actual in zip(uninterrupted, utterances, strict=True):
            a, b = (clock.parse_iso(expected[key]) for key in ("start", "end"))
            c, d = (clock.parse_iso(actual[key]) for key in ("start", "end"))
            intersection = (min(b, d) - max(a, c)).total_seconds()
            union = (max(b, d) - min(a, c)).total_seconds()
            assert intersection / union > 0.95
    finally:
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        whisper.close()
        llama.close()


@pytest.mark.looptime(False)
async def test_speech_dictation_uses_second_llama_slot(temp_root):
    started = asyncio.Event()
    # The fake uses a thread per request, like the server's slots. Another
    # host's ambient cleanup holds the first one.
    slow = pair("llama-cleanup-ambient")
    release = threading.Event()

    class HeldBatchServer(inference.ReplayServer):
        def _next_pair(self, method, path):
            selected = super()._next_pair(method, path)
            if (
                selected is not None
                and selected["response"] is self.pairs[0]["response"]
            ):
                assert release.wait(timeout=15), "batch was never released"
            return selected

    dic = pair("llama-cleanup-dictation")
    server = HeldBatchServer([slow, dic])
    task = None
    try:
        configure(temp_root, server, server)
        source = dic["request"]["body"]["messages"][1]["content"]
        source = source.removeprefix("<transcript>").removesuffix("</transcript>")
        streams.append(
            streams.day_path(temp_root / "state/asr/whisper", clock.utc_now().date()),
            {
                "input": "dic-test",
                "channel": "dic",
                "start": clock.iso(),
                "end": clock.iso(),
                "outcome": "ok",
                "text": source,
                "language": "en",
            },
        )

        async def ambient():
            started.set()
            return await inference.LlamaClient(
                server.url + inference.LLAMA_PATH
            ).complete([{"role": "user", "content": "Ambient text"}])

        task = asyncio.create_task(ambient())
        await started.wait()
        while not server.requests:
            await clock.sleep(0.005)
        # Keep the event loop free while odsodctl runs in another process.
        await asyncio.to_thread(drain, "cleanup")
        assert not task.done(), "dictation waited for the batch request"
        result = read(temp_root, "text")
        assert len(result) == 1 and result[0]["outcome"] == "ok"
        release.set()
        await task
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        server.close()
