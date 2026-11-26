from __future__ import annotations

from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    State,
    StatusReport,
)
from odsod_daemon.components.tray import menu

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
    assert model.action == "resume"


def test_menu_offers_pause_when_running():
    assert menu.build(report()).action == "pause"
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


def test_menu_offers_sync_toggle_only_on_a_satellite():
    assert menu.build(report()).sync is None
    assert menu.build(report(sync="running")).sync == "pause-sync"
    assert menu.build(report(sync="paused")).sync == "resume-sync"
    assert menu.text("pause-sync") == "Pause sync"
    assert menu.command("resume-sync") == ["sync", "resume"]
    assert menu.command("pause") == ["pause", "--by", "tray"]
