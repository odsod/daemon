"""Run: launch a listed command in its own systemd scope.

The app then lives outside the session service's cgroup, so a restart of the
service never kills it. A start that exits non-zero within 2 s gives one log
line.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import sys
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, Protocol

from odsod_daemon.components.shortcuts.contract import Shortcut
from odsod_daemon.lib import clock

LOG = logging.getLogger(__name__)

START_WINDOW_S = 2.0


class Process(Protocol):
    async def wait(self) -> int: ...


Spawn = Callable[[Sequence[str], IO[bytes]], Awaitable[Process]]


def unit_name(name: str, suffix: str) -> str:
    """``[odsod] meet`` and ``1a2b`` give ``app-odsod-meet-1a2b.scope``."""
    short = name.removeprefix("[odsod]").strip()
    short = re.sub(r"[^A-Za-z0-9]+", "-", short).strip("-") or "app"
    return f"app-odsod-{short}-{suffix}.scope"


def argv(shortcut: Shortcut, suffix: str) -> list[str]:
    return [
        "systemd-run",
        "--user",
        "--scope",
        f"--unit={unit_name(shortcut.name, suffix)}",
        "--collect",
        "--",
        *shortcut.command,
    ]


def environment(env: Mapping[str, str], directory: str) -> dict[str, str]:
    """``env`` with ``directory`` first on ``PATH``, unless it is there."""
    entries = [entry for entry in env.get("PATH", "").split(":") if entry]
    if directory not in entries:
        entries.insert(0, directory)
    return {**env, "PATH": ":".join(entries)}


async def spawn(command: Sequence[str], stderr: IO[bytes]) -> Process:
    # The user manager PATH may lack odsodctl; it sits next to this interpreter.
    return await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=stderr,
        start_new_session=True,
        env=environment(os.environ, str(Path(sys.executable).parent)),
    )


def _first_line(stderr: IO[bytes]) -> str:
    stderr.seek(0)
    line = stderr.readline(500).decode(errors="replace").strip()
    return line or "(no stderr)"


async def launch(shortcut: Shortcut, *, start: Spawn = spawn) -> None:
    """Start the command, then watch it for the start window."""
    command = argv(shortcut, secrets.token_hex(4))
    LOG.info("run %s: %s", shortcut.name, " ".join(shortcut.command))
    # A file, not a pipe: the app keeps its stderr after this service stops.
    with tempfile.TemporaryFile() as stderr:
        try:
            process = await start(command, stderr)
        except OSError as error:
            LOG.warning("run %s: start failed: %s", shortcut.name, error)
            return
        try:
            async with clock.timeout(START_WINDOW_S):
                code = await process.wait()
        except TimeoutError:
            return
        if code != 0:
            LOG.warning(
                "run %s: start failed: exit %d: %s",
                shortcut.name,
                code,
                _first_line(stderr),
            )
