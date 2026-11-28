"""ADR-0008: a shortcuts failure never stops the session service."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from types import ModuleType

import pytest

from odsod_daemon import components
from odsod_daemon.components import shortcuts
from odsod_daemon.lib import clock
from odsod_daemon.services.runner import ServiceSpec, run_service


def ticking() -> tuple[ModuleType, list[float]]:
    """A component that stands for dictation: it ticks once a second."""
    ticks: list[float] = []

    async def run(_config: object, *, once: bool = False) -> None:
        while True:
            ticks.append(clock.monotonic())
            await clock.sleep(1)

    module = ModuleType(f"{components.__name__}.ticking")
    vars(module)["SUBSYSTEM"] = "session"
    vars(module)["run"] = run
    return module, ticks


@pytest.mark.parametrize("outcome", ["raise", "return"])
async def test_failure_retries_and_other_components_keep_running(
    temp_root: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    tries: list[bool] = []

    async def serve(*, once: bool = False) -> None:
        tries.append(once)
        if outcome == "raise":
            raise RuntimeError("no session bus")

    monkeypatch.setattr(shortcuts, "serve", serve)
    other, ticks = ticking()
    service = asyncio.create_task(
        run_service(ServiceSpec("session", [other, shortcuts]))
    )
    await asyncio.sleep(shortcuts.RETRY_S * 3 + 1)
    assert not service.done()
    service.cancel()
    with suppress(asyncio.CancelledError):
        await service
    assert len(tries) == 4
    assert len(ticks) > shortcuts.RETRY_S * 3


async def test_once_logs_a_failure_and_returns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def serve(*, once: bool = False) -> None:
        raise RuntimeError("no session bus")

    monkeypatch.setattr(shortcuts, "serve", serve)
    with caplog.at_level(logging.ERROR, logger=shortcuts.__name__):
        await shortcuts.run(None, once=True)
    assert [r.message for r in caplog.records] == [
        "shortcuts failed; try again in 10 s"
    ]
