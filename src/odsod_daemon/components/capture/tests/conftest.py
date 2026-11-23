"""Fixtures for the capture component tests."""

from __future__ import annotations

import asyncio

import pytest

from odsod_daemon.components.capture.tests.helpers import (
    WALL_BASE,
    FakePwRecord,
    FakeSource,
)
from odsod_daemon.lib import clock


@pytest.fixture
def virtual_wall(monkeypatch: pytest.MonkeyPatch) -> float:
    """Tie ``clock.wall`` to the virtual event loop clock."""
    monkeypatch.setattr(
        clock, "wall", lambda: WALL_BASE + asyncio.get_running_loop().time()
    )
    return WALL_BASE


@pytest.fixture
def fake_pw() -> FakePwRecord:
    return FakePwRecord()


@pytest.fixture
def fake_source() -> FakeSource:
    return FakeSource()
