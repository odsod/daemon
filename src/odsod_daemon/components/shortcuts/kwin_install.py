"""Render the KWin package, compare it with the installed one, install it.

KWin belongs to shortcuts, so shortcuts installs its own script at session
start. An equal package on disk means no tool call and no reload, so no chord
drops on a restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

from odsod_daemon.components.shortcuts.contract import LIST_PATH
from odsod_daemon.lib import clock

LOG = logging.getLogger(__name__)

PLUGIN_ID = "odsod-daemon"
TEMPLATE = Path(__file__).with_name("kwin")
SCRIPT = Path("contents/code/main.js")
PLACEHOLDER = "/*@shortcuts@*/ []"
TRIES = 3
BACKOFF_S = 1.0

Runner = Callable[[Sequence[str]], Awaitable[None]]
Reload = Callable[[], Awaitable[None]]


def installed_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    home = Path(env.get("HOME", str(Path.home())))
    data_home = Path(env.get("XDG_DATA_HOME", home / ".local/share"))
    return data_home / "kwin/scripts" / PLUGIN_ID


def render(dest: Path, list_path: Path = LIST_PATH) -> None:
    """Copy the template to ``dest`` with the list in place of the placeholder."""
    shutil.copytree(TEMPLATE, dest, dirs_exist_ok=True)
    shortcuts = json.loads(list_path.read_text(encoding="utf-8"))["shortcuts"]
    script = dest / SCRIPT
    source = script.read_text(encoding="utf-8")
    if source.count(PLACEHOLDER) != 1:
        raise ValueError(f"{script}: expected one {PLACEHOLDER!r}")
    rendered = source.replace(PLACEHOLDER, json.dumps(shortcuts, indent=2))
    script.write_text(rendered, encoding="utf-8")


def _files(root: Path) -> dict[Path, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def same(rendered: Path, installed: Path) -> bool:
    """True if both trees hold the same files with the same bytes."""
    return installed.is_dir() and _files(rendered) == _files(installed)


async def run_tool(command: Sequence[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip().splitlines()[:1]
        raise RuntimeError(f"{command[0]} exit {process.returncode}: {detail}")


def _enable(value: bool) -> list[str]:
    return [
        "kwriteconfig6",
        "--file",
        "kwinrc",
        "--group",
        "Plugins",
        "--key",
        f"{PLUGIN_ID}Enabled",
        "true" if value else "false",
    ]


async def _install(rendered: Path, upgrade: bool, run: Runner, reload: Reload) -> None:
    mode = "--upgrade" if upgrade else "--install"
    await run(["kpackagetool6", "--type=KWin/Script", mode, str(rendered)])
    await run(_enable(False))
    await reload()
    await run(_enable(True))
    await reload()


async def ensure(
    *,
    run: Runner = run_tool,
    reload: Reload,
    installed: Path | None = None,
    list_path: Path = LIST_PATH,
) -> bool:
    """Install and reload the script if it differs. Return True when current.

    A failed step gets three tries with backoff, then one log line.
    """
    installed = installed_dir() if installed is None else installed
    with tempfile.TemporaryDirectory() as tmp:
        rendered = Path(tmp) / PLUGIN_ID
        render(rendered, list_path)
        if same(rendered, installed):
            LOG.info("kwin script: up to date")
            return True
        error: Exception | None = None
        for attempt in range(TRIES):
            if attempt:
                await clock.sleep(BACKOFF_S * 2 ** (attempt - 1))
            try:
                await _install(rendered, installed.is_dir(), run, reload)
            except Exception as caught:
                error = caught
                continue
            LOG.info("kwin script: installed and reloaded")
            return True
        LOG.warning("kwin script: install failed after %d tries: %s", TRIES, error)
        return False


async def reconfigure(bus: MessageBus) -> None:
    """Ask KWin to reload its config and plugins."""
    reply = await bus.call(
        Message(
            destination="org.kde.KWin",
            path="/KWin",
            interface="org.kde.KWin",
            member="reconfigure",
        )
    )
    if reply is not None and reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"reconfigure: {reply.error_name}: {reply.body}")
