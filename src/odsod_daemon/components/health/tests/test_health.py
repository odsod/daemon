from datetime import timedelta
from pathlib import Path

import pytest

from odsod_daemon.components.health import units
from odsod_daemon.components.health.backlog import BacklogTracker
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import Reason, Severity
from odsod_daemon.components.health.evaluate import evaluate
from odsod_daemon.components.health.snapshot import Snapshot, gather
from odsod_daemon.components.install.contract import InstallRecord, PreviousCommit
from odsod_daemon.lib import audio, clock, documents, paths, streams, systemd

NOW = clock.parse_iso("2026-11-23T12:30:00Z")
OLD = clock.iso(NOW - timedelta(seconds=1000))


def state(name, active="active", age=10):
    return systemd.UnitState(
        units.unit(name),
        "system" if name == "keys" else "user",
        active,
        "running",
        "success",
        int((NOW.timestamp() - age) * 1_000_000),
    )


def healthy():
    return Snapshot(
        now=NOW,
        units={name: state(name) for name in units.SERVICES},
        newest_audio={"mic": clock.iso(NOW), "sys": clock.iso(NOW)},
    )


def reason(severity: Severity = "warning", code="inference-unreachable"):
    return Reason(
        code=code,
        severity=severity,
        service="capture",
        since=OLD,
        message="The microphone is silent.",
    )


@pytest.mark.parametrize(
    "faults,mode,paused,expected,exit_code",
    [
        ([], "idle", False, "running", 0),
        ([reason("mark", "mic-muted")], "idle", False, "mic-muted", 0),
        # Only zeros is a hardware mute: the same mark, not a Warning.
        ([reason("mark", "mic-silent")], "idle", False, "mic-muted", 0),
        ([], "idle", True, "paused", 0),
        ([reason("mark", "mic-muted")], "idle", True, "paused", 0),
        ([reason()], "idle", True, "warning", 1),
        ([reason()], "dictating", True, "dictating", 0),
        ([reason("error", "capture-stalled")], "dictating", True, "error", 2),
    ],
)
def test_state_precedence(faults, mode, paused, expected, exit_code):
    snapshot = healthy()
    snapshot.faults = faults
    snapshot.status = {"mode": mode, "keys": "connected"}
    snapshot.units["session"] = state("session")
    if paused:
        snapshot.paused_since = OLD
        snapshot.units["capture"] = state("capture", "inactive")
    report = evaluate(snapshot, ControlConfig())
    assert (report.state, report.exit_code) == (expected, exit_code)


@pytest.mark.parametrize("missing", units.SERVICES)
def test_partial_build_requires_shipped_units(missing):
    snapshot = healthy()
    report = evaluate(snapshot, ControlConfig())
    assert report.state == "running"
    assert all(
        not s.expected
        for s in report.services
        if s.unit.removeprefix("odsod-daemon-").removesuffix(".service")
        not in units.SERVICES
    )
    snapshot.units[missing] = None
    assert evaluate(snapshot, ControlConfig()).exit_code == 2


def test_unit_grace_failure_rollback_and_scope(monkeypatch):
    monkeypatch.setattr(units, "SERVICES", (*units.SERVICES, "keys"))
    snapshot = healthy()
    snapshot.units["keys"] = state("keys", "inactive", age=2)
    assert evaluate(snapshot, ControlConfig()).exit_code == 0
    snapshot.units["keys"] = state("keys", "failed", age=0)
    snapshot.previous = PreviousCommit(commit="old", source="git", replaced_at=OLD)
    report = evaluate(snapshot, ControlConfig())
    assert report.exit_code == 2
    assert report.reasons[0].fix == "sudo systemctl restart odsod-daemon-keys"
    assert "daemon:setup old" in report.reasons[0].message


def test_dev_and_no_graphical_session():
    snapshot = healthy()
    snapshot.graphical = False
    snapshot.units["capture"] = None
    snapshot.install = InstallRecord(
        source="dev", commit="a", workspace="/tmp/work", installed_at=OLD
    )
    report = evaluate(snapshot, ControlConfig())
    assert report.state == "running"
    assert report.dev
    assert report.dictation.reason == "session-down"


def test_audio_stale():
    snapshot = healthy()
    snapshot.units["capture"] = state("capture", age=2000)
    snapshot.newest_audio["mic"] = OLD
    report = evaluate(snapshot, ControlConfig())
    assert report.exit_code == 2
    assert report.reasons[0].code == "audio-stale"
    assert report.reasons[0].since == OLD


@pytest.mark.parametrize("age,exit_code", [(0.2, 0), (120, 0), (121, 2)])
def test_audio_stale_after_capture_resume(age, exit_code):
    snapshot = healthy()
    snapshot.units["capture"] = state("capture", age=age)
    snapshot.newest_audio = {"mic": OLD, "sys": OLD}
    report = evaluate(snapshot, ControlConfig())
    assert report.exit_code == exit_code
    stale = [r for r in report.reasons if r.code == "audio-stale"]
    assert len(stale) == (2 if exit_code else 0)
    assert all(r.since == clock.iso(NOW - timedelta(seconds=age)) for r in stale)


@pytest.mark.parametrize("asleep_ago,exit_code", [(5, 0), (120, 0), (121, 2)])
def test_audio_stale_counts_from_a_wake(asleep_ago, exit_code):
    """Time asleep is not a stall: a lid close leaves old audio and a running
    capture unit (owner report, 2026-11-25)."""
    snapshot = healthy()
    snapshot.units["capture"] = state("capture", age=2000)
    snapshot.newest_audio = {"mic": OLD, "sys": OLD}
    snapshot.resumed = clock.iso(NOW - timedelta(seconds=asleep_ago))
    report = evaluate(snapshot, ControlConfig())
    assert report.exit_code == exit_code


@pytest.mark.parametrize(
    "capture_age,covered,seconds",
    [(10, False, 0), (601, False, 601), (10, True, 1000)],
)
async def test_mid_hour_start_without_coverage(
    tmp_path: Path, capture_age, covered, seconds
):
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    source = systemd.FakeUnitStates()
    source.set(state("capture", age=capture_age))
    source.set(state("pipeline"))
    tracker = BacklogTracker(roots.state)
    for channel in audio.CHANNELS:
        file = audio.hour_file(roots.state, channel, NOW)
        file.parent.mkdir(parents=True)
        with file.open("wb") as handle:
            handle.truncate(1800 * audio.BYTES_PER_SECOND)
        if covered:
            tracker.coverage[channel] = OLD
    snapshot = await gather(
        roots, source, now=NOW, tracker=tracker, settings=ControlConfig()
    )
    report = evaluate(snapshot, ControlConfig())
    assert report.backlog.count == 0
    assert report.backlog.seconds == seconds * len(audio.CHANNELS)
    assert report.exit_code == (1 if seconds else 0)
    assert [r.code for r in report.reasons] == (["backlog"] if seconds else [])


def test_backlog_incremental_and_ten_days(tmp_path: Path):
    then = NOW - timedelta(days=10)
    utterance = {
        "id": "a",
        "start": clock.iso(then),
        "end": clock.iso(then + timedelta(seconds=12)),
    }
    file = streams.day_path(tmp_path / "utterances/ambient", then.date())
    streams.append(file, utterance)
    tracker = BacklogTracker(tmp_path)
    tracker.rebuild(NOW)
    result = tracker.report(NOW, {}, 600)
    assert result.count == 1
    assert result.seconds == 12
    assert result.oldest == utterance["start"]
    snapshot = healthy()
    snapshot.backlog, snapshot.oldest_end = result, tracker.oldest_end
    assert evaluate(snapshot, ControlConfig()).state == "warning"
    out = streams.day_path(tmp_path / "text", NOW.date())
    out.parent.mkdir()
    out.write_text('{"input":"a"}')
    tracker.update(NOW)
    assert tracker.report(NOW, {}, 600).count == 1
    with out.open("a") as handle:
        handle.write("\n")
    tracker.update(NOW)
    rebuilt = BacklogTracker(tmp_path)
    rebuilt.rebuild(NOW)
    assert tracker.report(NOW, {}, 600) == rebuilt.report(NOW, {}, 600)
    assert tracker.report(NOW, {}, 600).count == 0


@pytest.mark.parametrize("gap,seconds", [(4, 0), (601, 601)])
def test_unsegmented_gap(tmp_path: Path, gap, seconds):
    tracker = BacklogTracker(tmp_path)
    tracker.coverage["mic"] = clock.iso(NOW - timedelta(seconds=gap))
    assert tracker.report(NOW, {"mic": clock.iso(NOW)}, 600).seconds == seconds


async def test_snapshot_active_health_and_audio_stat(tmp_path: Path):
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    documents.write_json(
        roots.config_file,
        {
            "common": {
                "inference": {
                    "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
                    "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
                }
            }
        },
    )
    source = systemd.FakeUnitStates()
    for name in ("capture", "pipeline"):
        source.set(state(name))
    source.set(
        systemd.UnitState("graphical-session.target", "user", "active", "active", "", 0)
    )
    health = roots.run / "health/capture.json"
    documents.write(health, "broken")
    documents.write(
        roots.run / "status.json", '{"mode":"dictating","keys":"connected"}'
    )
    for channel in ("mic", "sys"):
        file = audio.hour_file(roots.state, channel, NOW)
        file.parent.mkdir(parents=True)
        with file.open("wb") as handle:
            handle.truncate(1800 * audio.BYTES_PER_SECOND)
    snapshot = await gather(roots, source, now=NOW)
    assert snapshot.newest_audio["mic"] == clock.iso(NOW)
    assert snapshot.faults[0].code == "health-unreadable"
    assert not snapshot.status
    source.set(state("capture", "inactive"))
    assert not (await gather(roots, source, now=NOW)).faults


def test_backlog_window_rolls_at_midnight(tmp_path: Path):
    tracker = BacklogTracker(tmp_path, retention_days=1)
    streams.append(
        streams.day_path(tmp_path / "utterances/dictation", NOW.date()),
        {
            "id": "a",
            "start": OLD,
            "end": clock.iso(NOW),
        },
    )
    tracker.rebuild(NOW)
    assert tracker.report(NOW, {}, 600).count == 1
    tracker.update(NOW + timedelta(days=1))
    assert tracker.report(NOW + timedelta(days=1), {}, 600).count == 0


def test_ambient_recording_ac12_only_zeros_is_a_mute_mark():
    from odsod_daemon.components.health.snapshot import SEVERITY

    assert SEVERITY["mic-silent"] == "mark"


@pytest.mark.parametrize("server", units.SERVERS)
def test_server_units_expected_only_on_the_inference_host(server):
    """PRD health-and-control: the server units show in status."""
    snapshot = healthy()
    snapshot.units[server] = None
    report = evaluate(snapshot, ControlConfig())
    assert report.state == "running"
    listed = {s.unit: s for s in report.services}
    assert not listed[units.unit(server)].expected
    snapshot.inference = True
    for name in units.SERVERS:
        snapshot.units[name] = state(name)
    assert evaluate(snapshot, ControlConfig()).state == "running"
    snapshot.units[server] = state(server, "failed")
    report = evaluate(snapshot, ControlConfig())
    assert report.state == "error"
    assert report.reasons[0].code == "unit-failed"
    assert report.reasons[0].fix == f"systemctl --user restart odsod-daemon-{server}"


@pytest.mark.parametrize("enabled", [True, False])
async def test_snapshot_reads_the_inference_role(tmp_path: Path, enabled):
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    documents.write_json(roots.config_file, {"inference": {"enabled": enabled}})
    source = systemd.FakeUnitStates()
    source.set(state("llama", "failed"))
    snapshot = await gather(
        roots,
        source,
        now=NOW,
        tracker=BacklogTracker(roots.state),
        settings=ControlConfig(),
    )
    assert snapshot.inference is enabled
    llama = snapshot.units["llama"]
    assert (llama is not None and llama.active_state == "failed") is enabled


async def test_snapshot_reads_satellite_pipeline_faults(tmp_path: Path):
    """ADR-0024: faults of a satellite host root show on the base, with the host."""
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    documents.write_json(
        roots.config_file,
        {
            "common": {
                "inference": {
                    "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
                    "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
                }
            }
        },
    )
    source = systemd.FakeUnitStates()
    source.set(state("pipeline"))
    documents.write_json(
        roots.state / "hosts/laptop/run/health/pipeline.json",
        {
            "service": "pipeline",
            "ts": clock.iso(NOW),
            "faults": [
                {
                    "code": "inference-unreachable",
                    "since": clock.iso(NOW),
                    "message": "whisper is down.",
                    "fix": None,
                }
            ],
        },
    )
    snapshot = await gather(roots, source, now=NOW)
    assert [(f.code, f.message) for f in snapshot.faults] == [
        ("inference-unreachable", "laptop: whisper is down.")
    ]


@pytest.mark.parametrize("role,seconds", [("base", 3600.0), ("satellite", 0.0)])
async def test_satellite_audio_is_no_unsegmented_backlog(tmp_path: Path, role, seconds):
    """ADR-0024: a satellite segments nothing, so its audio is no backlog."""
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    common = {
        "role": role,
        "base": "desktop",
        "inference": {
            "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
            "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
        },
    }
    documents.write_json(roots.config_file, {"common": common})
    for channel in ("mic", "sys"):
        file = audio.hour_file(roots.state, channel, NOW)
        file.parent.mkdir(parents=True)
        with file.open("wb") as handle:
            handle.truncate(1800 * audio.BYTES_PER_SECOND)
    snapshot = await gather(roots, systemd.FakeUnitStates(), now=NOW)
    assert snapshot.backlog.seconds == seconds


@pytest.mark.parametrize(
    "role,paused,sync",
    [
        ("base", True, None),
        ("satellite", False, "running"),
        ("satellite", True, "paused"),
    ],
)
async def test_sync_pause_is_a_mark_on_a_satellite(tmp_path: Path, role, paused, sync):
    """ADR-0024: a paused sync shows in status, and the state stays OK."""
    roots = paths.Roots(tmp_path / "state", tmp_path / "run", tmp_path / "config")
    common = {
        "role": role,
        "base": "desktop",
        "inference": {
            "whisper_url": "http://127.0.0.1:8178/v1/audio/transcriptions",
            "llama_url": "http://127.0.0.1:8179/v1/chat/completions",
        },
    }
    documents.write_json(roots.config_file, {"common": common})
    if paused:
        documents.write_json(roots.state / "sync-paused", {"since": OLD})
    documents.write_json(roots.run / "sync.json", {"last_ok": OLD})
    snapshot = await gather(roots, systemd.FakeUnitStates(), now=NOW)
    report = evaluate(snapshot, ControlConfig())
    assert report.sync == sync
    assert (report.base, report.last_sync) == (
        (None, None) if sync is None else ("desktop", OLD)
    )
    marks = [r for r in report.reasons if r.code == "sync-paused"]
    assert [(r.severity, r.since) for r in marks] == (
        [("mark", OLD)] if sync == "paused" else []
    )
