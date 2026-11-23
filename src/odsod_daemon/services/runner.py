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

from odsod_daemon.lib import clock, config, healthfile, paths, systemd


class ComponentNotBuilt(RuntimeError):
    """The component has no ``run`` yet."""


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    components: Sequence[ModuleType]


@dataclass(frozen=True)
class PreparedComponent:
    runner: Callable[..., Awaitable[Any]]
    section: Any


def load_component(name: str) -> ModuleType:
    module_name = name.replace("-", "_")
    if not module_name or not module_name.replace("_", "").isalnum():
        raise ValueError(f"bad component name: {name!r}")
    return importlib.import_module(f"odsod_daemon.components.{module_name}")


def prepare_component(module: ModuleType) -> PreparedComponent:
    """Resolve a component's ``run`` and config section before it starts."""
    runner: Callable[..., Awaitable[Any]] | None = getattr(module, "run", None)
    if runner is None:
        raise ComponentNotBuilt(f"{module.__name__}: no run()")
    model = getattr(module, "CONFIG_MODEL", None)
    section: Any = None
    if model is not None:
        section = config.section(module.SUBSYSTEM, model)
    return PreparedComponent(runner=runner, section=section)


async def run_prepared(prepared: PreparedComponent, *, once: bool = False) -> None:
    await prepared.runner(prepared.section, once=once)


async def run_component(module: ModuleType, *, once: bool = False) -> None:
    """Load a component's config section and run it."""
    await run_prepared(prepare_component(module), once=once)


async def _mark_started(
    prepared: PreparedComponent, started: asyncio.Event, *, once: bool
) -> None:
    started.set()
    await run_prepared(prepared, once=once)


async def _watchdog(interval_s: float) -> None:
    while True:
        await clock.sleep(interval_s)
        systemd.sd_notify("WATCHDOG=1")


async def run_service(spec: ServiceSpec, *, once: bool = False) -> None:
    prepared = [prepare_component(module) for module in spec.components]
    if once:
        for item in prepared:
            await run_prepared(item, once=True)
        return

    health = paths.roots().run / f"health/{spec.name}.json"
    if health.exists():
        # Faults of the previous run void at start; components set them again.
        healthfile.HealthFile(health, spec.name).rewrite_empty()
    started = [asyncio.Event() for _ in prepared]
    owns_watchdog = any(
        getattr(module, "WATCHDOG_OWNER", False) for module in spec.components
    )
    async with asyncio.TaskGroup() as group:
        for item, event in zip(prepared, started, strict=True):
            group.create_task(_mark_started(item, event, once=False))
        await asyncio.gather(*(event.wait() for event in started))
        systemd.sd_notify("READY=1")
        interval = systemd.watchdog_interval()
        if interval is not None and not owns_watchdog:
            group.create_task(_watchdog(interval))
