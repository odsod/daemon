"""Run the components of one service in one process.

A service is composition only. Its components run in one ``asyncio.TaskGroup``.
``READY=1`` goes out when every component has started. ``WATCHDOG=1`` goes out
every half ``WATCHDOG_USEC``.

On the base, the ``per_host`` components also run once per satellite host
root. On a satellite, only the ``satellite`` components run (ADR-0024).
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


HOST_SCAN_S = 60.0


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    components: Sequence[ModuleType]
    # Of ``components``: the ones that also run per satellite host root.
    per_host: Sequence[ModuleType] = ()
    # The components on a satellite. None: the service is the same there.
    satellite: Sequence[ModuleType] | None = None

    def plan(self, role: str) -> tuple[list[ModuleType], list[ModuleType]]:
        """Return (components for this host, components per host root)."""
        if role == "satellite" and self.satellite is not None:
            return list(self.satellite), []
        if role == "satellite":
            return list(self.components), []
        return list(self.components), [m for m in self.components if m in self.per_host]


def role_of(spec: ServiceSpec) -> str:
    if not spec.per_host and spec.satellite is None:
        return "base"
    return config.load_common().role


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


def _void_health(name: str) -> None:
    health = paths.roots().run / f"health/{name}.json"
    if health.exists():
        # Faults of the previous run void at start; components set them again.
        healthfile.HealthFile(health, name).rewrite_empty()


def _start_host(
    group: asyncio.TaskGroup, name: str, host: str, prepared: list[PreparedComponent]
) -> None:
    # Tasks copy the context when they are created, so they keep the host root.
    with paths.host(host):
        _void_health(name)
        for item in prepared:
            group.create_task(run_prepared(item))


async def _scan_hosts(
    group: asyncio.TaskGroup,
    name: str,
    prepared: list[PreparedComponent],
    known: set[str],
) -> None:
    while True:
        await clock.sleep(HOST_SCAN_S)
        for host in paths.satellites():
            if host not in known:
                known.add(host)
                _start_host(group, name, host, prepared)


async def run_service(spec: ServiceSpec, *, once: bool = False) -> None:
    modules, per_host = spec.plan(role_of(spec))
    prepared = [prepare_component(module) for module in modules]
    hosted = [prepare_component(module) for module in per_host]
    hosts = paths.satellites() if hosted else []
    if once:
        for item in prepared:
            await run_prepared(item, once=True)
        for host in hosts:
            with paths.host(host):
                for item in hosted:
                    await run_prepared(item, once=True)
        return

    _void_health(spec.name)
    started = [asyncio.Event() for _ in prepared]
    owns_watchdog = any(getattr(module, "WATCHDOG_OWNER", False) for module in modules)
    async with asyncio.TaskGroup() as group:
        for item, event in zip(prepared, started, strict=True):
            group.create_task(_mark_started(item, event, once=False))
        await asyncio.gather(*(event.wait() for event in started))
        if hosted:
            for host in hosts:
                _start_host(group, spec.name, host, hosted)
            group.create_task(_scan_hosts(group, spec.name, hosted, set(hosts)))
        systemd.sd_notify("READY=1")
        interval = systemd.watchdog_interval()
        if interval is not None and not owns_watchdog:
            group.create_task(_watchdog(interval))
