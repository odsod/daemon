from __future__ import annotations

import asyncio
import json
import socket
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from odsod_daemon.services.runner import (
    ServiceSpec,
    load_component,
    run_service,
)


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


def test_load_component_accepts_the_architecture_name() -> None:
    module = load_component("notify-failed")
    assert module.__name__ == "odsod_daemon.components.notify_failed"


def test_load_component_rejects_a_bad_name() -> None:
    with pytest.raises(ValueError, match="bad component name"):
        load_component("../lib")


class Section(BaseModel):
    value: int


async def test_service_does_not_report_ready_before_config_is_valid(
    temp_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (temp_root / "config" / "config.json").write_text(
        json.dumps({"runtime": {"value": "nope"}}), encoding="utf-8"
    )
    path = tmp_path / "notify.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(0.2)
    monkeypatch.setenv("NOTIFY_SOCKET", str(path))
    called: list[bool] = []

    async def run(_config: object, *, once: bool = False) -> None:
        called.append(True)

    module = component("invalid", run)
    vars(module)["CONFIG_MODEL"] = Section
    try:
        with pytest.raises(ValidationError):
            await run_service(ServiceSpec("test", [module]))
        with pytest.raises(TimeoutError):
            receiver.recv(64)
    finally:
        receiver.close()

    assert called == []


async def test_once_drains_in_component_order() -> None:
    seen = []

    async def upstream(_config, *, once=False):
        await asyncio.sleep(0)
        seen.append("upstream")

    async def downstream(_config, *, once=False):
        assert seen == ["upstream"]
        seen.append("downstream")

    await run_service(
        ServiceSpec(
            "test",
            [component("upstream", upstream), component("downstream", downstream)],
        ),
        once=True,
    )
    assert seen == ["upstream", "downstream"]
