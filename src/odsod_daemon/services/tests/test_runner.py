from __future__ import annotations

import asyncio
import socket
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from odsod_daemon.services.runner import ServiceSpec, run_service


def component(name: str, body: Any) -> ModuleType:
    module = ModuleType(name)
    vars(module)["SUBSYSTEM"] = "runtime"
    vars(module)["run"] = body
    return module


def blocking_component() -> ModuleType:
    async def run(_config: object, *, once: bool = False) -> None:
        await asyncio.Event().wait()

    return component("blocking", run)


def returning_component() -> ModuleType:
    async def run(_config: object, *, once: bool = False) -> None:
        return None

    return component("returning", run)


@pytest.mark.looptime(False)
async def test_service_sends_ready_then_watchdog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "notify.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(3)
    monkeypatch.setenv("NOTIFY_SOCKET", str(path))
    monkeypatch.setenv("WATCHDOG_USEC", "200000")

    spec = ServiceSpec("test", [blocking_component(), blocking_component()])
    service = asyncio.create_task(run_service(spec))
    try:
        ready = await asyncio.to_thread(receiver.recv, 64)
        ping = await asyncio.to_thread(receiver.recv, 64)
    finally:
        service.cancel()
        with suppress(asyncio.CancelledError):
            await service
        receiver.close()

    assert ready == b"READY=1"
    assert ping == b"WATCHDOG=1"


async def test_service_without_notify_socket_does_not_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    await run_service(ServiceSpec("test", [returning_component()]))


async def test_once_runs_components_and_exits() -> None:
    seen: list[bool] = []

    async def run(_config: object, *, once: bool = False) -> None:
        seen.append(once)

    await run_service(ServiceSpec("test", [component("once", run)]), once=True)
    assert seen == [True]
