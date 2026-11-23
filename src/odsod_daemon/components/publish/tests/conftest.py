"""A fake clock for publish tests."""

from __future__ import annotations

import pytest

from odsod_daemon.components.publish.tests.helpers import FakeClock
from odsod_daemon.lib import clock


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(clock, "utc_now", fake.utc_now)
    monkeypatch.setattr(clock, "monotonic", fake.mono)
    return fake
