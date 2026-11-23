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


def reason(severity: Severity = "warning", code="mic-silent"):
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
