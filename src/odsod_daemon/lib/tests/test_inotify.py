from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

import pytest

from odsod_daemon.lib import inotify


def instances() -> int:
    count = 0
    for fd in os.listdir("/proc/self/fd"):
        with contextlib.suppress(FileNotFoundError):
            count += os.readlink(f"/proc/self/fd/{fd}") == "anon_inode:inotify"
    return count


@pytest.mark.looptime(False)
async def test_watches_share_one_instance(tmp_path: Path) -> None:
    """The kernel allows 256 inotify instances per user. One instance per
    watch made the base pipeline hold 97 with one satellite (2026-11-25)."""
    before = instances()
    watches = []
    for n in range(20):
        directory = tmp_path / f"d{n % 5}"
        directory.mkdir(exist_ok=True)
        watches.append(inotify.DirectoryWatch(directory))
    try:
        assert instances() - before == 1
    finally:
        for watch in watches:
            watch.close()
    assert instances() == before


@pytest.mark.looptime(False)
async def test_change_wakes_only_watches_of_its_directory(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    first, second, other = (
        inotify.DirectoryWatch(a),
        inotify.DirectoryWatch(a),
        inotify.DirectoryWatch(b),
    )
    try:
        (a / "x").write_text("1")
        await asyncio.wait_for(first.changed.wait(), 2)
        await asyncio.wait_for(second.changed.wait(), 2)
        assert not other.changed.is_set()
        first.close()
        second.changed.clear()
        (a / "y").write_text("1")
        await asyncio.wait_for(second.changed.wait(), 2)
    finally:
        for watch in (first, second, other):
            watch.close()
