"""Run a sync pass every interval and report when sync falls behind."""

from __future__ import annotations

import asyncio
import logging

from odsod_daemon.components.sync import plan
from odsod_daemon.components.sync.config import SyncConfig
from odsod_daemon.lib import clock, config, healthfile, paths

log = logging.getLogger(__name__)
CODE = "sync-behind"


async def run_pass(commands: list[list[str]]) -> str | None:
    """Run the commands in order. Return the first error, or None."""
    for command in commands:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
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
    last_ok = clock.monotonic()
    while True:
        commands = plan.commands(roots, common.host, common.base, settings.remote_state)
        error = await run_pass(commands)
        now = clock.monotonic()
        if error is None:
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
