from __future__ import annotations

from datetime import timedelta

from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    State,
    StatusReport,
)
from odsod_daemon.components.tray import menu
from odsod_daemon.lib import clock

NOW = "2026-11-23T12:30:00.000Z"
STATES: tuple[State, ...] = (
    "error",
    "dictating",
    "warning",
    "paused",
    "mic-muted",
    "running",
    "unknown",
)


def report(**changes):
    values = {
        "state": "running",
        "exit_code": 0,
        "backlog": Backlog(count=0, seconds=0),
        "mode": "idle",
        "dictation": DictationState(available=True),
        "ts": NOW,
    }
    values.update(changes)
    return StatusReport(**values)


def reason(**changes) -> Reason:
    return Reason(
        code=str(changes.get("code", "audio-stale")),
        severity="error",
        service=str(changes.get("service", "capture")),
        since=NOW,
        message="The mic audio has stopped advancing.",
        fix="systemctl --user restart odsod-daemon-capture",
    )


def test_tooltip_names_the_state_and_first_reason():
    assert menu.tooltip(report()) == "Running"
    item = reason()
    assert menu.tooltip(report(state="error", reasons=[item])) == (
        f"Error: {item.message}"
    )


def test_menu_lists_reasons_dictation_and_the_action():
    item = reason()
    model = menu.build(
        report(
            state="error",
            reasons=[item],
            dictation=DictationState(available=False, reason="paused"),
            paused_since=NOW,
        )
    )
    assert [line.text for line in model.lines] == [
        f"{item.message} Since {menu.local_time(NOW)}. {item.fix}",
        "Dictation unavailable: paused.",
    ]
    assert [(t.key, t.checked) for t in model.toggles] == [("recording", False)]


def test_menu_offers_pause_when_running():
    assert menu.build(report()).toggles == (
        menu.Toggle("recording", "Recording", True),
    )
    assert menu.build(report()).lines == ()


def test_every_state_and_dev_mark_has_an_icon():
    for state in STATES:
        for dev in (False, True):
            path = menu.icon_path(report(state=state, dev=dev))
            assert path.is_file(), path
            shown = "error" if state == "unknown" else state
            assert path.name == f"{shown}{'-dev' if dev else ''}.svg"


def test_unreadable_service_states_show_the_error_icon():
    assert menu.icon_path(report(state="unknown")).name == "error.svg"
    assert menu.icon_path(report(state="unknown", dev=True)).name == "error-dev.svg"


def test_toggles_show_the_state_and_flip_it():
    """The check is the state; the text says since when or how recent."""
    paused = clock.iso(clock.parse_iso(NOW) - timedelta(minutes=10))
    model = menu.build(report(paused_since=paused))
    assert model.toggles[0].text == (
        f"Recording · paused since {menu.short_time(paused, NOW)}"
    )
    assert menu.command(model.toggles[0]) == ["resume", "--by", "tray"]
    assert menu.command(menu.Toggle("recording", "", True)) == [
        "pause",
        "--by",
        "tray",
    ]


def test_sync_toggle_only_on_a_satellite():
    assert [t.key for t in menu.build(report()).toggles] == ["recording"]
    recent = clock.iso(clock.parse_iso(NOW) - timedelta(seconds=8))
    running = menu.build(report(sync="running", base="desktop", last_sync=recent))
    assert running.toggles[1] == menu.Toggle("sync", "Sync to desktop · just now", True)
    assert menu.command(running.toggles[1]) == ["sync", "pause"]
    old = clock.iso(clock.parse_iso(NOW) - timedelta(minutes=7))
    assert menu.build(report(sync="running", base="desktop", last_sync=old)).toggles[
        1
    ].text == ("Sync to desktop · 7 min ago")
    mark = Reason(
        code="sync-paused",
        severity="mark",
        service="pipeline",
        since=old,
        message="Sync to the base is paused.",
    )
    paused = menu.build(report(sync="paused", base="desktop", reasons=[mark]))
    assert paused.lines == ()
    assert paused.toggles[1] == menu.Toggle(
        "sync", f"Sync to desktop · paused since {menu.short_time(old, NOW)}", False
    )
    assert menu.command(paused.toggles[1]) == ["sync", "resume"]


def test_ago_is_coarse():
    def at(seconds):
        return clock.iso(clock.parse_iso(NOW) - timedelta(seconds=seconds))

    assert [menu.ago(at(s), NOW) for s in (5, 59, 61, 3599, 7300)] == [
        "just now",
        "just now",
        "1 min ago",
        "59 min ago",
        "2 h ago",
    ]
