from __future__ import annotations

from datetime import timedelta

import pytest

from odsod_daemon.components.health import units
from odsod_daemon.components.health.backlog import BacklogTracker
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    Severity,
    State,
    StatusReport,
)
from odsod_daemon.components.tray.worker import TrayWorker
from odsod_daemon.lib import audio, clock, documents, paths, systemd

NOW = clock.utc_now()
OLD = clock.iso(NOW - timedelta(seconds=30))


def state(name, active="active"):
    from odsod_daemon.components.health import units

    return systemd.UnitState(
        units.unit(name),
        "system" if name == "keys" else "user",
        active,
        "running" if active == "active" else "dead",
        "success",
        int(NOW.timestamp() * 1_000_000),
    )


def source():
    result = systemd.FakeUnitStates()
    for name in ("capture", "pipeline", "session", "tray"):
        result.set(state(name))
    result.set(
        systemd.UnitState("graphical-session.target", "user", "active", "active", "", 0)
    )
    return result


def worker(temp_root, reports, notifications):
    roots = paths.roots()
    return TrayWorker(
        roots,
        source(),
        ControlConfig(),
        report=reports.append,
        notify=lambda item: notifications.append(item) or True,
        tracker=BacklogTracker(roots.state),
    )


def report(
    *reasons: Reason, state: State = "running", paused_since: str | None = None
) -> StatusReport:
    return StatusReport(
        state=state,
        exit_code=0,
        reasons=list(reasons),
        backlog=Backlog(count=0, seconds=0),
        mode="idle",
        dictation=DictationState(available=True),
        paused_since=paused_since,
        ts=OLD,
    )


def error(
    code: str = "capture-stalled",
    service: str = "capture",
    severity: Severity = "error",
) -> Reason:
    return Reason(
        code=code,
        severity=severity,
        service=service,
        since=OLD,
        message=f"The {service} has a fault.",
        fix=f"systemctl --user restart odsod-daemon-{service}",
    )


@pytest.mark.looptime(False)
async def test_evaluate_once_reads_health_and_status(temp_root, monkeypatch):
    monkeypatch.setattr(units, "SERVICES", (*units.SERVICES, "session"))
    roots = paths.roots()
    documents.write_json(
        roots.run / "status.json", {"mode": "dictating", "keys": "connected"}
    )
    for channel in audio.CHANNELS:
        file = audio.hour_file(roots.state, channel, NOW)
        file.parent.mkdir(parents=True)
        with file.open("wb") as handle:
            handle.truncate(
                int(
                    (NOW - audio.hour_start(NOW)).total_seconds()
                    * audio.BYTES_PER_SECOND
                )
            )
    reports = []
    item = worker(temp_root, reports, [])
    await item.evaluate_once()
    assert reports[-1].state == "dictating"
    assert reports[-1].dictation.available


@pytest.mark.looptime(False)
async def test_apply_status_ignores_invalid_and_unchanged(temp_root):
    roots = paths.roots()
    item = worker(temp_root, [], [])
    await item.evaluate_once()
    path = roots.run / "status.json"
    documents.write_json(path, {"mode": "dictating", "keys": "connected"})
    assert item._apply_status(path)
    assert not item._apply_status(path)
    documents.write(path, "broken")
    assert not item._apply_status(path)
    documents.write_json(path, {"mode": "sideways", "keys": "connected"})
    assert not item._apply_status(path)


def test_notifications_follow_new_error_causes(temp_root):
    notifications = []
    item = worker(temp_root, [], notifications)
    first = report(error(), state="error")
    item.notify_new(first)
    item.notify_new(first)
    assert len(notifications) == 1
    assert notifications[0].title == "odsod-daemon: capture"
    assert "restart odsod-daemon-capture" in notifications[0].body
    item.notify_new(report())
    item.notify_new(first)
    assert len(notifications) == 2
    item.notify_new(report(error("unit-failed"), state="error"))
    assert len(notifications) == 2
    item.notify_new(report(error("audio-stale", "capture"), state="error"))
    assert len(notifications) == 3


def test_unknown_report_names_the_read_error(temp_root):
    reports = []
    item = worker(temp_root, reports, [])
    item._publish_unknown(RuntimeError("manager unavailable"))
    assert reports[-1].state == "unknown"
    assert reports[-1].exit_code == 3
    assert "manager unavailable" in reports[-1].reasons[0].message
