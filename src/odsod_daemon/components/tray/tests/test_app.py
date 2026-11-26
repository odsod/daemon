from __future__ import annotations

import asyncio
import threading

import pytest

from odsod_daemon.components.health import units
from odsod_daemon.components.health.backlog import BacklogTracker
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    StatusReport,
)
from odsod_daemon.components.tray import app
from odsod_daemon.components.tray.app import Bridge, TrayApp
from odsod_daemon.components.tray.worker import TrayWorker
from odsod_daemon.lib import audio, clock, documents, paths, systemd

NOW = clock.utc_now()


def state(name, active="active"):
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


def report(**changes):
    values = {
        "state": "paused",
        "exit_code": 0,
        "backlog": Backlog(count=0, seconds=0),
        "mode": "idle",
        "dictation": DictationState(available=False, reason="paused"),
        "ts": clock.iso(),
    }
    values.update(changes)
    return StatusReport(**values)


def wait_for(qt_app, predicate, timeout=2.0):
    deadline = clock.monotonic() + timeout
    while clock.monotonic() < deadline:
        qt_app.processEvents()
        if predicate():
            return True
        threading.Event().wait(0.005)
    return False


def test_menu_and_pause_command(qt_app):
    calls = []
    tray = TrayApp(start=lambda args: calls.append(args) or True)
    tray.apply(
        report(
            state="error",
            paused_since=clock.iso(),
            reasons=[
                Reason(
                    code="audio-stale",
                    severity="error",
                    service="capture",
                    since=clock.iso(),
                    message="The mic audio has stopped advancing.",
                    fix="systemctl --user restart odsod-daemon-capture",
                )
            ],
        )
    )
    labels = [a.text() for a in tray.menu.actions() if not a.isSeparator()]
    assert labels[0].startswith("The mic audio has stopped advancing.")
    recording = tray.menu.actions()[-1]
    assert recording.text().startswith("Recording · paused since ")
    assert recording.isCheckable() and not recording.isChecked()
    assert not tray.icon.icon().isNull()
    assert tray.tooltip.startswith("Error:")
    recording.trigger()
    assert calls == [["resume", "--by", "tray"]]
    # The check follows the report, not the click.
    assert not recording.isChecked()
    tray.apply(report(state="running", paused_since=None))
    recording = tray.menu.actions()[-1]
    assert (recording.text(), recording.isChecked()) == ("Recording", True)
    recording.trigger()
    assert calls[-1] == ["pause", "--by", "tray"]
    assert not tray.icon.icon().isNull()


def test_satellite_menu_toggles_sync(qt_app):
    calls = []
    tray = TrayApp(start=lambda args: calls.append(args) or True)
    tray.apply(report(state="running", paused_since=None, sync="running", base="desk"))
    labels = [a.text() for a in tray.menu.actions() if not a.isSeparator()]
    assert labels[-2:] == ["Recording", "Sync to desk"]
    tray.menu.actions()[-1].trigger()
    assert calls == [["sync", "pause"]]
    tray.apply(report(state="running", paused_since=None, sync="paused", base="desk"))
    sync = tray.menu.actions()[-1]
    assert (sync.text(), sync.isChecked()) == ("Sync to desk · paused", False)
    sync.trigger()
    assert calls[-1] == ["sync", "resume"]


def test_unchanged_items_update_in_place(qt_app):
    """An open menu stays open: a new text or check keeps the same items."""
    tray = TrayApp(start=lambda _args: True)
    tray.apply(report(state="running", paused_since=None))
    before = tray.menu.actions()
    tray.apply(report(state="running", paused_since=None, ts=clock.iso()))
    assert tray.menu.actions() == before
    tray.apply(report(state="paused", paused_since=clock.iso()))
    assert tray.menu.actions() == before
    assert not before[-1].isChecked()
    assert before[-1].text().startswith("Recording · paused since ")


def test_odsodctl_resolves_next_to_the_interpreter(tmp_path, monkeypatch):
    python = tmp_path / "bin" / "python"
    python.parent.mkdir()
    monkeypatch.setattr(app.sys, "executable", str(python))
    assert app.odsodctl() == "odsodctl"
    (tmp_path / "bin" / "odsodctl").touch()
    assert app.odsodctl() == str(tmp_path / "bin" / "odsodctl")


def test_dev_mark_selects_the_dev_icon(qt_app):
    tray = TrayApp(start=lambda _args: True)
    tray.apply(report(state="warning", dev=True, paused_since=None))
    assert not tray.icon.icon().isNull()
    assert "Warning" in tray.tooltip


@pytest.mark.looptime(False)
def test_mode_change_reaches_the_icon_slot(temp_root, qt_app, monkeypatch):
    monkeypatch.setattr(units, "SERVICES", (*units.SERVICES, "session", "tray"))
    roots = paths.roots()
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
    path = roots.run / "status.json"
    documents.write_json(path, {"mode": "idle", "keys": "connected"})
    bridge = Bridge()
    tray = TrayApp(start=lambda _args: True)
    bridge.report.connect(tray.apply)
    background = TrayWorker(
        roots,
        source(),
        ControlConfig(tray_interval_s=5, backlog_warning_s=100_000),
        report=bridge.report.emit,
        tracker=BacklogTracker(roots.state),
    )
    thread = threading.Thread(target=lambda: asyncio.run(background.run()), daemon=True)
    thread.start()
    try:
        assert wait_for(qt_app, lambda: tray.state == "running"), (
            tray.state,
            tray.tooltip,
        )
        assert background.following.wait(1)
        threading.Event().wait(0.05)
        started = clock.monotonic()
        documents.write_json(path, {"mode": "dictating", "keys": "connected"})
        assert wait_for(qt_app, lambda: tray.state == "dictating")
        elapsed = clock.monotonic() - started
        assert elapsed <= 0.2, f"mode change took {elapsed:.3f}s"
    finally:
        background.stop()
        thread.join(timeout=2)
        qt_app.processEvents()
