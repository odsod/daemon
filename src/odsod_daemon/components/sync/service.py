"""Run a sync pass every interval and report when sync falls behind."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from odsod_daemon.components.sync import flag, plan
from odsod_daemon.components.sync.config import SyncConfig
from odsod_daemon.lib import clock, config, healthfile, paths

log = logging.getLogger(__name__)
CODE = "sync-behind"
PAUSED = "paused"
# How often a running rsync checks the pause flag.
POLL_S = 1.0


async def run_pass(
    commands: list[list[str]], paused: Callable[[], bool] = lambda: False
) -> str | None:
    """Run the commands in order. Return the first error, PAUSED, or None.

    A pause stops the running rsync within POLL_S. ``--append`` resumes it
    from the bytes the base already has."""
    for command in commands:
        if paused():
            return PAUSED
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        done = asyncio.ensure_future(process.communicate())
        while not (await asyncio.wait({done}, timeout=POLL_S))[0]:
            if paused():
                process.kill()
                await done
                return PAUSED
        _, stderr = done.result()
        if process.returncode != 0:
            lines = stderr.decode(errors="replace").strip().splitlines()
            return f"rsync exit {process.returncode}: {lines[-1] if lines else ''}"
    return None


async def run(settings: SyncConfig, *, once: bool = False) -> None:
    common = config.load_common()
    if common.role != "satellite" or common.base is None:
        return
    roots = paths.roots().ensure()
    health = healthfile.HealthFile(roots.run / "health/pipeline.json", "pipeline")

    def paused() -> bool:
        return (roots.state / flag.NAME).exists()

    last_ok = clock.monotonic()
    while True:
        commands = plan.commands(roots, common.host, common.base, settings.remote_state)
        error = await run_pass(commands, paused)
        now = clock.monotonic()
        if error is None or error == PAUSED:
            # A pause is the owner's choice, not a fault: count from its end.
            last_ok = now
            if health.clear(CODE):
                health.rewrite()
        else:
            log.warning("sync to %s failed: %s", common.base, error)
            if now - last_ok >= settings.behind_after_s:
                minutes = round((now - last_ok) / 60)
                health.set(
                    CODE,
                    f"No sync to {common.base} for {minutes} min: {error}",
                    fix=f"Check that `ssh {common.base}` works from this host.",
                )
                health.rewrite()
        if once:
            return
        await clock.sleep(settings.interval_s)
