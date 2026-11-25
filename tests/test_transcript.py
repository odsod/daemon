"""Fixture audio through speech and transcript, with process kills and replay."""

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import wave
from datetime import timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.transcript.contract import parse_file
from odsod_daemon.lib import audio, clock, inference, streams

AUDIO = Path(__file__).parent / "testdata/audio"
PAIRS = Path(inference.__file__).parent / "testdata"


def records(root, stream):
    return [
        record
        for file in sorted((root / "state" / stream).glob("*.jsonl"))
        for record in streams.read_day(file)
    ]


def fixture_audio(root, channel, name, start, state=None):
    with wave.open(str(AUDIO / f"{name}.wav")) as wav:
        pcm = wav.readframes(wav.getnframes())
    file = audio.hour_file(state or root / "state", channel, start)
    file.parent.mkdir(parents=True, exist_ok=True)
    # A silent tail closes live segmentation without an idle wait.
    file.write_bytes(pcm + bytes(32000))
    return start + timedelta(seconds=len(pcm) / 32000)


def replay(name):
    pair = json.loads((PAIRS / f"{name}.json").read_text())
    pair["response"]["delay_ms"] = 100
    return pair


def drain():
    result = subprocess.run(
        ["timeout", "25", "uv", "run", "odsodctl", "run", "pipeline", "--once"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.looptime(False)
@pytest.mark.parametrize(
    "boundary", ["segmentation", "transcription", "cleanup", "transcript"]
)
async def test_transcript_speech_kill_recovery(temp_root, boundary):
    whisper = inference.ReplayServer([replay("whisper-en-verbose") for _ in range(30)])
    llama = inference.ReplayServer(
        [replay("llama-cleanup-dictation") for _ in range(30)]
    )
    process = None
    try:
        (temp_root / "config/config.json").write_text(
            json.dumps(
                {
                    "common": {
                        "host": "system-test",
                        "inference": {
                            "whisper_url": whisper.url + inference.WHISPER_PATH,
                            "llama_url": llama.url + inference.LLAMA_PATH,
                        },
                    },
                    "signals": {"cdp_ports": []},
                }
            )
        )
        start = audio.hour_start(clock.utc_now())
        fixture_audio(temp_root, "sys", "en-study-in-scarlet", start)
        end = fixture_audio(temp_root, "mic", "en-chinese-feet", start)
        streams.append(
            streams.day_path(
                temp_root / "state/utterances/dictation", clock.utc_now().date()
            ),
            {
                "kind": "utterance",
                "ts": clock.iso(),
                "id": "dic-fixture",
                "channel": "dic",
                "start": clock.iso(start),
                "end": clock.iso(end),
            },
        )

        def output_lines():
            return [
                line
                for file in (temp_root / "state/documents/transcripts").glob("*.md")
                for line in parse_file(file.read_text())
            ]

        def reached():
            if boundary == "transcript":
                return bool(output_lines())
            stream = {
                "segmentation": "utterances/ambient",
                "transcription": "asr/whisper",
                "cleanup": "text",
            }[boundary]
            return bool(records(temp_root, stream))

        process = subprocess.Popen(
            ["timeout", "25", "uv", "run", "odsodctl", "run", "pipeline"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        async with clock.timeout(15):
            while not reached():
                assert process.poll() is None, process.communicate()[1].decode()
                await clock.sleep(0.005)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        await asyncio.to_thread(drain)
        texts = records(temp_root, "text")
        output = output_lines()
        assert texts and len(output) == len(texts)
        assert len({line.key for line in output}) == len(output)
        assert {line.key for line in output} == {r["input"] for r in texts}
        by_id = {r["input"]: r for r in texts}
        for line in output:
            source = by_id[line.key]
            assert source["outcome"] == "ok"
            assert line.text == " ".join(source["text"].split())
            assert line.tag == source["channel"]
            assert (
                line.time.timestamp()
                == clock.parse_iso(source["start"]).replace(microsecond=0).timestamp()
            )
        assert sum(line.tag == "dic" for line in output) == 1
        assert not any(line.tag == "mic" for line in output)
        files = list((temp_root / "state/documents/transcripts").glob("*.md"))
        assert len(files) == 1
        original = files[0].read_bytes()
        await asyncio.to_thread(drain)
        assert files[0].read_bytes() == original
        assert not list((temp_root / "state/events/signals").glob("*.jsonl"))
    finally:
        if process is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        whisper.close()
        llama.close()


@pytest.mark.looptime(False)
async def test_base_makes_a_transcript_per_host_root(temp_root):
    """ADR-0024: the base processes a satellite's synced files in its host root."""
    whisper = inference.ReplayServer([replay("whisper-en-verbose") for _ in range(30)])
    llama = inference.ReplayServer(
        [replay("llama-cleanup-dictation") for _ in range(30)]
    )
    try:
        (temp_root / "config/config.json").write_text(
            json.dumps(
                {
                    "common": {
                        "host": "desktop",
                        "inference": {
                            "whisper_url": whisper.url + inference.WHISPER_PATH,
                            "llama_url": llama.url + inference.LLAMA_PATH,
                        },
                    },
                    "signals": {"cdp_ports": []},
                }
            )
        )
        start = audio.hour_start(clock.utc_now())
        satellite = temp_root / "state/hosts/laptop"
        fixture_audio(temp_root, "sys", "en-study-in-scarlet", start)
        fixture_audio(temp_root, "sys", "en-study-in-scarlet", start, satellite)
        await asyncio.to_thread(drain)
        documents = {
            root: sorted(
                (root / "state/documents/transcripts").glob("*.md")
                if root is temp_root
                else (root / "documents/transcripts").glob("*.md")
            )
            for root in (temp_root, satellite)
        }
        assert [p.name.endswith("-desktop.md") for p in documents[temp_root]] == [True]
        assert [p.name.endswith("-laptop.md") for p in documents[satellite]] == [True]
        base_lines = parse_file(documents[temp_root][0].read_text())
        satellite_lines = parse_file(documents[satellite][0].read_text())
        assert base_lines and [line.text for line in base_lines] == [
            line.text for line in satellite_lines
        ]
    finally:
        whisper.close()
        llama.close()
