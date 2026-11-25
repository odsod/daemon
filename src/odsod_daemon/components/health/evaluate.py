"""Pure health rules and state precedence."""

from odsod_daemon.components.health import units
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import (
    DictationState,
    Reason,
    ServiceState,
    State,
    StatusReport,
)
from odsod_daemon.components.health.snapshot import Snapshot, timestamp
from odsod_daemon.lib import clock


def evaluate(snapshot: Snapshot, config: ControlConfig) -> StatusReport:
    reasons = list(snapshot.faults)
    services = []
    for name in units.NAMES:
        raw = snapshot.units.get(name)
        active = raw.active_state if raw else "missing"
        since = timestamp(raw)
        expected = units.expected(
            name,
            graphical=snapshot.graphical,
            paused=snapshot.paused_since is not None,
            inference=snapshot.inference,
        )
        services.append(
            ServiceState(
                unit=units.unit(name),
                scope="system" if name == "keys" else "user",
                expected=expected,
                active_state=active,
                sub_state=raw.sub_state if raw else "missing",
                since=since,
            )
        )
        age = (snapshot.now - clock.parse_iso(since)).total_seconds()
        if expected and (
            active == "failed" or (active != "active" and age > config.unit_grace_s)
        ):
            code = "unit-failed" if active == "failed" else "unit-down"
            message = f"The {name} unit is {active}."
            if snapshot.previous:
                message += (
                    " If this started after the upgrade, run "
                    f"`mise run daemon:setup {snapshot.previous.commit}` "
                    "in the machine repo."
                )
            reasons.append(
                Reason(
                    code=code,
                    severity="error",
                    service=name,
                    since=since,
                    message=message,
                    fix=units.fix(name),
                )
            )
    capture = snapshot.units.get("capture")
    if capture is not None and capture.active_state == "active":
        for channel in ("mic", "sys"):
            # Time asleep is not a stall: count from the last wake too.
            since = max(
                snapshot.newest_audio.get(channel) or timestamp(capture),
                timestamp(capture),
                snapshot.resumed or timestamp(capture),
                key=clock.parse_iso,
            )
            if (
                snapshot.now - clock.parse_iso(since)
            ).total_seconds() > config.audio_stale_s:
                reasons.append(
                    Reason(
                        code="audio-stale",
                        severity="error",
                        service="capture",
                        since=since,
                        message=f"The {channel} audio has stopped advancing.",
                        fix=units.fix("capture"),
                    )
                )
    if (
        snapshot.oldest_end
        and (snapshot.now - clock.parse_iso(snapshot.oldest_end)).total_seconds()
        > config.backlog_warning_s
    ):
        reasons.append(
            Reason(
                code="backlog",
                severity="warning",
                service="pipeline",
                since=snapshot.oldest_end,
                message=(
                    f"The backlog holds {snapshot.backlog.count} utterances "
                    f"and {snapshot.backlog.seconds:g} seconds."
                ),
            )
        )
    session = snapshot.units.get("session")
    session_active = session is not None and session.active_state == "active"
    mode = (
        "dictating"
        if session_active and snapshot.status.get("mode") == "dictating"
        else "idle"
    )
    keys = snapshot.status.get("keys") if session_active else None
    dictation = DictationState(
        available=keys == "connected",
        reason=keys or "session-down",
    )
    state: State = "running"
    if any(r.severity == "error" for r in reasons):
        state = "error"
    elif mode == "dictating":
        state = "dictating"
    elif any(r.severity == "warning" for r in reasons):
        state = "warning"
    elif snapshot.paused_since is not None and (
        capture is None or capture.active_state != "active"
    ):
        state = "paused"
    elif any(r.code in ("mic-muted", "mic-silent") for r in reasons):
        state = "mic-muted"
    installed = snapshot.install
    return StatusReport(
        state=state,
        exit_code={"error": 2, "warning": 1}.get(state, 0),
        reasons=reasons,
        services=services,
        newest_audio=snapshot.newest_audio,
        backlog=snapshot.backlog,
        mode=mode,
        dictation=dictation,
        paused_since=snapshot.paused_since,
        dev=installed is not None and installed.source == "dev",
        commit=installed.commit if installed else None,
        workspace=installed.workspace if installed else None,
        ts=clock.iso(snapshot.now),
    )
