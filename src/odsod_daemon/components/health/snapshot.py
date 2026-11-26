"""Read each health source once into an evaluation snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from odsod_daemon.components.health import units
from odsod_daemon.components.health.backlog import BacklogTracker
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import Backlog, Reason, Severity
from odsod_daemon.components.install.contract import InstallRecord, PreviousCommit
from odsod_daemon.components.servers.contract import Inference
from odsod_daemon.lib import audio, clock, config, documents, paths, systemd

SEVERITY: dict[str, Severity] = {
    "capture-stalled": "error",
    "keys-socket-missing": "error",
    "mic-muted": "mark",
    "mic-silent": "mark",
    "inference-unreachable": "warning",
    "parakeet-unavailable": "warning",
    "target-missing": "warning",
    "no-speaking-indicator": "warning",
    "interactions-waiting": "warning",
    "mute-failed": "warning",
    "stale-mutes-cleared": "warning",
    "sync-behind": "warning",
}


@dataclass
class Snapshot:
    now: datetime
    graphical: bool = True
    # This host runs the inference servers (config section inference).
    inference: bool = False
    units: dict[str, systemd.UnitState | None] = field(default_factory=dict)
    faults: list[Reason] = field(default_factory=list)
    newest_audio: dict[str, str | None] = field(default_factory=dict)
    # The last wake from suspend that the reading process saw.
    resumed: str | None = None
    backlog: Backlog = field(default_factory=lambda: Backlog(count=0, seconds=0))
    oldest_end: str | None = None
    status: dict[str, Any] = field(default_factory=dict)
    paused_since: str | None = None
    # None on a base: it has no sync (ADR-0024).
    sync_paused_since: str | None = None
    satellite: bool = False
    base: str | None = None
    last_sync: str | None = None
    install: InstallRecord | None = None
    previous: PreviousCommit | None = None


def optional(path):
    try:
        return documents.read_json(path)
    except FileNotFoundError:
        return None


async def gather(
    roots: paths.Roots,
    source: systemd.UnitStateSource,
    *,
    now: datetime | None = None,
    tracker: BacklogTracker | None = None,
    settings: ControlConfig | None = None,
) -> Snapshot:
    now = now or clock.utc_now()
    settings = settings or config.section("control", ControlConfig, roots=roots)
    # Like install: a host with no config file runs no server.
    inference = (
        roots.config_file.exists()
        and config.section("inference", Inference, roots=roots).enabled
    )
    result = Snapshot(now=now, inference=inference)
    graphical = await source.get("graphical-session.target")
    result.graphical = graphical is not None and graphical.active_state == "active"
    paused = optional(roots.run / "paused")
    if paused is not None:
        result.paused_since = paused["since"]
    for service in units.NAMES:
        shipped = units.shipped(service, inference=inference)
        state = (
            await source.get(
                units.unit(service), scope="system" if service == "keys" else "user"
            )
            if shipped
            else None
        )
        result.units[service] = state
        if state is None or state.active_state != "active":
            continue
        # ADR-0024: the pipeline also runs per satellite host root.
        sources = [("", roots.run / "health" / f"{service}.json")]
        if service == "pipeline":
            hosts = roots.state / paths.HOSTS
            sources += [
                (f"{host}: ", hosts / host / "run/health/pipeline.json")
                for host in paths.satellites(state=roots.state)
            ]
        try:
            for prefix, path in sources:
                health = optional(path)
                for fault in health["faults"] if health is not None else []:
                    result.faults.append(
                        Reason(
                            **{k: fault[k] for k in ("code", "since", "fix")},
                            message=prefix + fault["message"],
                            service=service,
                            severity=SEVERITY[fault["code"]],
                        )
                    )
        except OSError, ValueError, KeyError, TypeError:
            result.faults.append(
                Reason(
                    code="health-unreadable",
                    severity="warning",
                    service=service,
                    since=clock.iso(now),
                    message=f"Health file of {service} is unreadable.",
                )
            )
    session = result.units.get("session")
    if session is not None and session.active_state == "active":
        try:
            status = optional(roots.run / "status.json")
            if (
                status is not None
                and status["mode"] in ("idle", "dictating")
                and status["keys"]
                in ("connected", "paused", "no-inference", "no-socket")
            ):
                result.status = status
        except OSError, ValueError, KeyError, TypeError:
            pass
    starts = {}
    for channel in audio.CHANNELS:
        end = None
        for hour in (audio.hour_start(now) - timedelta(hours=1), audio.hour_start(now)):
            file = audio.hour_file(roots.state, channel, hour)
            try:
                size = file.stat().st_size
            except FileNotFoundError:
                continue
            covered = hour + timedelta(seconds=audio.seconds_for(size))
            end = max(end, covered) if end else covered
            starts.setdefault(channel, clock.iso(hour))
        result.newest_audio[channel] = clock.iso(end) if end else None
    capture = result.units.get("capture")
    if capture is not None and capture.active_state == "active":
        starts = {
            channel: max(start, timestamp(capture), key=clock.parse_iso)
            for channel, start in starts.items()
        }
    if tracker is None:
        common = config.load_common(roots)
        tracker = BacklogTracker(roots.state, common.retention_days)
        tracker.rebuild(now)
    # ADR-0024: a satellite segments nothing; the base does its ambient work.
    try:
        common = config.load_common(roots)
    except config.ConfigError, ValueError:
        common = None
    satellite = common is not None and common.role == "satellite"
    result.satellite = satellite
    if common is not None and satellite:
        result.base = common.base
        flag = optional(roots.state / "sync-paused")
        if flag is not None:
            result.sync_paused_since = flag["since"]
        try:
            status = optional(roots.run / "sync.json")
            result.last_sync = status["last_ok"] if status else None
        except OSError, ValueError, KeyError, TypeError:
            pass
    result.backlog = tracker.report(
        now,
        {} if satellite else result.newest_audio,
        settings.backlog_warning_s,
        starts,
    )
    result.oldest_end = tracker.oldest_end
    current = optional(roots.state / "install/current")
    previous = optional(roots.state / "install/previous-commit")
    result.install = InstallRecord.model_validate(current) if current else None
    result.previous = PreviousCommit.model_validate(previous) if previous else None
    return result


def timestamp(state: systemd.UnitState | None) -> str:
    seconds = state.state_change_timestamp / 1_000_000 if state else 0
    return clock.iso(datetime.fromtimestamp(seconds, UTC))
