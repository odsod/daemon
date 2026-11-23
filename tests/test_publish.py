"""End to end: a finished transcript becomes one copy in a temp target."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from odsod_daemon.lib import clock, streams


def publish(root: Path) -> None:
    result = subprocess.run(
        ["timeout", "30", "uv", "run", "odsodctl", "run", "publish", "--once"],
        capture_output=True,
        text=True,
        timeout=40,
        cwd=Path(__file__).parents[1],
        env=os.environ | {"ODSOD_DAEMON_ROOT": str(root)},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def deliveries(root: Path, target: str) -> list[dict]:
    directory = root / "state/published" / target
    return [
        record
        for path in sorted(directory.glob("*.jsonl"))
        for record in streams.read_day(path)
        if record.get("kind") == "delivery"
    ]


def test_finished_transcript_reaches_a_target_once(temp_root) -> None:
    target = temp_root / "vault"
    target.mkdir()
    (temp_root / "config/config.json").write_text(
        json.dumps(
            {
                "publishing": {
                    "targets": [
                        {
                            "name": "vault",
                            "dir": str(target),
                            "types": ["transcripts"],
                        }
                    ]
                }
            }
        )
    )
    # The target appears in config before any document is finished.
    publish(temp_root)

    name = "2026-11-23-system-test.md"
    text = "# Transcript 2026-11-23\n"
    document = temp_root / "state/documents/transcripts" / name
    document.parent.mkdir(parents=True)
    document.write_text(text)
    streams.append(
        streams.day_path(
            temp_root / "state/finished/transcript", clock.utc_now().date()
        ),
        {
            "ts": clock.iso(),
            "kind": "finished",
            "document": name,
            "type": "transcripts",
        },
    )

    publish(temp_root)

    copy = target / name
    assert copy.read_text() == text
    before = (copy.stat().st_ino, copy.stat().st_mtime_ns)
    records = deliveries(temp_root, "vault")
    assert len(records) == 1
    assert records[0]["document"] == name
    assert records[0]["type"] == "transcripts"
    assert records[0]["bytes"] == len(text.encode())

    publish(temp_root)

    assert (copy.stat().st_ino, copy.stat().st_mtime_ns) == before
    assert len(deliveries(temp_root, "vault")) == 1
