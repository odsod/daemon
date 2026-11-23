from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from odsod_daemon.components.signals.platforms.meet import Meet
from odsod_daemon.components.signals.platforms.teams import Teams

DOM = Path(__file__).parent / "testdata" / "dom"
CHROME = (
    shutil.which("google-chrome")
    or shutil.which("google-chrome-stable")
    or shutil.which("chromium")
    or shutil.which("chromium-browser")
)

pytestmark = [
    pytest.mark.chrome,
    pytest.mark.skipif(CHROME is None, reason="Chromium not installed"),
]

_TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)


def evaluate(page: Path, expression: str, tmp_path: Path) -> str:
    assert CHROME is not None
    script = f"<script>document.title = 'SIGNALS:' + ({expression});</script>"
    source = page.read_text(encoding="utf-8")
    if "</body>" in source:
        source = source.replace("</body>", f"{script}</body>")
    else:
        source = source + script
    html_path = tmp_path / f"{page.stem}-page.html"
    html_path.write_text(source, encoding="utf-8")

    output = subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=1000",
            "--dump-dom",
            html_path.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    match = _TITLE.search(output)
    assert match is not None, output[:200]
    title = html.unescape(match.group(1))
    assert title.startswith("SIGNALS:"), title
    return title.removeprefix("SIGNALS:")


def test_meet_snapshot_reads_the_saved_page(tmp_path: Path) -> None:
    value = evaluate(DOM / "meet.html", Meet().snapshot_js(), tmp_path)
    tiles = Meet().parse_snapshot(value)
    assert [tile.name for tile in tiles] == ["Alice Smith", "Bob Jones"]
    assert "speaking-active" in tiles[0].classes


def test_meet_poll_reads_the_saved_page(tmp_path: Path) -> None:
    value = evaluate(DOM / "meet.html", Meet().poll_js("speaking-active"), tmp_path)
    tiles = Meet().parse_poll(value)
    assert [(tile.name, tile.speaking) for tile in tiles] == [
        ("Alice Smith", True),
        ("Bob Jones", False),
    ]


def test_teams_snapshot_reads_the_saved_page(tmp_path: Path) -> None:
    value = evaluate(DOM / "teams.html", Teams().snapshot_js(), tmp_path)
    tiles = Teams().parse_snapshot(value)
    assert [tile.name for tile in tiles] == [
        "Alice Direct",
        "Bob Nested",
        "Carol Wrapped",
    ]
    assert all(tile.classes for tile in tiles)


def test_teams_poll_reads_the_saved_page(tmp_path: Path) -> None:
    value = evaluate(DOM / "teams.html", Teams().poll_js("speaking-active"), tmp_path)
    tiles = Teams().parse_poll(value)
    assert [(tile.name, tile.speaking) for tile in tiles] == [
        ("Alice Direct", True),
        ("Bob Nested", False),
        ("Carol Wrapped", True),
    ]
