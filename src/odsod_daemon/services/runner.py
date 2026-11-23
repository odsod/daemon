"""Run the components of one service in one process.

A service is composition only. Its components run in one ``asyncio.TaskGroup``.
``READY=1`` goes out when every component has started. ``WATCHDOG=1`` goes out
every half ``WATCHDOG_USEC``.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from odsod_daemon.lib import clock, config, systemd


class ComponentNotBuilt(RuntimeError):
    """The component has no ``run`` yet."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    components: Sequence[ModuleType]


def load_component(name: str) -> ModuleType:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"bad component name: {name!r}")
    return importlib.import_module(f"odsod_daemon.components.{name}")


async def run_component(module: ModuleType, *, once: bool = False) -> None:
    """Load a component's config section and run it."""
    runner: Callable[..., Awaitable[Any]] | None = getattr(module, "run", None)
    if runner is None:
        raise ComponentNotBuilt(f"{module.__name__}: no run()")
    model = getattr(module, "CONFIG_MODEL", None)
    section: Any = None
    if model is not None:
        section = config.section(module.SUBSYSTEM, model)
    await runner(section, once=once)


async def _mark_started(
    module: ModuleType, started: asyncio.Event, *, once: bool
) -> None:
    started.set()
    await run_component(module, once=once)


async def _watchdog(interval_s: float) -> None:
    while True:
        await clock.sleep(interval_s)
        systemd.sd_notify("WATCHDOG=1")


async def run_service(spec: ServiceSpec, *, once: bool = False) -> None:
    if once:
        async with asyncio.TaskGroup() as group:
            for component in spec.components:
                group.create_task(run_component(component, once=True))
        return

    started = [asyncio.Event() for _ in spec.components]
    async with asyncio.TaskGroup() as group:
        for component, event in zip(spec.components, started, strict=True):
            group.create_task(_mark_started(component, event, once=False))
        await asyncio.gather(*(event.wait() for event in started))
        systemd.sd_notify("READY=1")
        interval = systemd.watchdog_interval()
        if interval is not None:
            group.create_task(_watchdog(interval))
