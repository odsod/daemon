import json

import pytest

from odsod_daemon.components.transcript.tests.test_core import ZONE
from odsod_daemon.lib import clock, streams


@pytest.fixture
def transcript_root(temp_root, monkeypatch):
    (temp_root / "config/config.json").write_text(
        json.dumps(
            {
                "common": {
                    "host": "test-host",
                    "inference": {
                        "whisper_url": "http://localhost:8178/v1/audio/transcriptions",
                        "llama_url": "http://localhost:8179/v1/chat/completions",
                    },
                }
            }
        )
    )
    monkeypatch.setattr(
        "odsod_daemon.components.transcript.writer.local_zone", lambda: ZONE
    )
    return temp_root


def append(root, stream, record):
    streams.append(
        streams.day_path(root / "state" / stream, clock.parse_iso(record["ts"]).date()),
        record,
    )
