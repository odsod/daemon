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


@pytest.mark.looptime(False)
async def test_a_watchdog_owner_component_suppresses_the_runner_ping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "notify.sock"
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(path))
    receiver.settimeout(0.5)
    monkeypatch.setenv("NOTIFY_SOCKET", str(path))
    monkeypatch.setenv("WATCHDOG_USEC", "100000")
    module = blocking_component()
    vars(module)["WATCHDOG_OWNER"] = True

    service = asyncio.create_task(run_service(ServiceSpec("test", [module])))
    try:
        assert await asyncio.to_thread(receiver.recv, 64) == b"READY=1"
        with pytest.raises(TimeoutError):
            await asyncio.to_thread(receiver.recv, 64)
    finally:
        service.cancel()
        with suppress(asyncio.CancelledError):
            await service
        receiver.close()


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


async def test_service_start_voids_old_faults(temp_root: Path) -> None:
    """ADR-0003: a restart rebuilds from files; old faults do not survive it."""
    from odsod_daemon.lib import documents, healthfile, paths

    path = paths.roots().run / "health/test.json"
    old = healthfile.HealthFile(path, "test")
    old.set("target-missing", "gone", key="vault")
    old.rewrite()
    service = asyncio.create_task(
        run_service(ServiceSpec("test", [blocking_component()]))
    )
    await asyncio.sleep(0.1)
    service.cancel()
    with suppress(asyncio.CancelledError):
        await service
    assert documents.read_json(path)["faults"] == []


def write_common(root: Path, **common: object) -> None:
    inference = {
        "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
        "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
    }
    (root / "config/config.json").write_text(
        json.dumps({"common": {"inference": inference, **common}})
    )


def recording_component(name: str, seen: list[tuple[str, str]]) -> ModuleType:
    from odsod_daemon.lib import paths

    async def run(_config: object, *, once: bool = False) -> None:
        seen.append((name, paths.current_host() or "-"))

    return component(name, run)


async def test_base_runs_per_host_components_for_each_satellite(
    temp_root: Path,
) -> None:
    """ADR-0024: the base runs the host components once per host root."""
    write_common(temp_root)
    (temp_root / "state/hosts/laptop").mkdir(parents=True)
    seen: list[tuple[str, str]] = []
    shared = recording_component("shared", seen)
    hosted = recording_component("hosted", seen)
    spec = ServiceSpec("test", [hosted, shared], per_host=[hosted])
    await run_service(spec, once=True)
    assert seen == [("hosted", "-"), ("shared", "-"), ("hosted", "laptop")]


async def test_satellite_runs_only_satellite_components(temp_root: Path) -> None:
    write_common(temp_root, role="satellite", base="desktop")
    (temp_root / "state/hosts/laptop").mkdir(parents=True)
    seen: list[tuple[str, str]] = []
    spec = ServiceSpec(
        "test",
        [recording_component("full", seen)],
        per_host=[],
        satellite=[recording_component("sync", seen)],
    )
    await run_service(spec, once=True)
    assert seen == [("sync", "-")]


@pytest.mark.looptime(False)
async def test_live_host_tasks_keep_their_host_root(temp_root: Path) -> None:
    write_common(temp_root)
    (temp_root / "state/hosts/laptop").mkdir(parents=True)
    seen: list[tuple[str, str]] = []
    done = asyncio.Event()

    async def run(_config: object, *, once: bool = False) -> None:
        from odsod_daemon.lib import paths

        await asyncio.sleep(0)
        seen.append(("hosted", paths.current_host() or "-"))
        if len(seen) == 2:
            done.set()
        await asyncio.Event().wait()

    hosted = component("hosted", run)
    service = asyncio.create_task(
        run_service(ServiceSpec("test", [hosted], per_host=[hosted]))
    )
    try:
        await asyncio.wait_for(done.wait(), 3)
    finally:
        service.cancel()
        with suppress(asyncio.CancelledError):
            await service
    assert sorted(seen) == [("hosted", "-"), ("hosted", "laptop")]
