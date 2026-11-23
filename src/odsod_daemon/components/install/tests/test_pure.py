from pathlib import Path

import pytest

from odsod_daemon.components.install.apply import changed, compare
from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.components.install.render import substitute
from odsod_daemon.components.install.source import candidate


def test_source_vcs_and_local(monkeypatch):
    assert candidate({"vcs_info": {"commit_id": "abc"}}).source == "git"
    monkeypatch.setattr("odsod_daemon.components.install.source._git", lambda *a: "abc")
    record = candidate({"url": "file:///tmp/a%20b"})
    assert record.workspace == "/tmp/a b"
    assert record.dirty
    assert changed(record, None)
    assert not changed(record, record)
    assert changed(record, record.model_copy(update={"commit": "def"}))
    with pytest.raises(ValueError):
        candidate({"url": "https://example.com/archive"})


def test_compare_writes_and_removes_only_owned_files(tmp_path: Path):
    unit = tmp_path / "odsod-daemon-capture.service"
    unrelated = tmp_path / "other.service"
    unrelated.write_text("leave")
    old = tmp_path / "odsod-daemon-old.service"
    old.write_text("old")
    dbus = tmp_path / "session.dbus"
    changes = compare({unit: "new"}, tmp_path, dbus)
    assert changes.writes == {unit: "new"}
    assert changes.removals == (old,)
    unit.write_text("new")
    old.unlink()
    assert not compare({unit: "new"}, tmp_path, dbus).units_changed
    assert unrelated.read_text() == "leave"


def test_substitution():
    assert substitute("ExecStart={{ctl}}", {"ctl": "/tmp/ctl"}) == "ExecStart=/tmp/ctl"
    with pytest.raises(ValueError):
        substitute("{{missing}}", {})


def test_candidate_identity_ignores_timestamp_and_dirty():
    record = InstallRecord(source="dev", commit="a", installed_at="now")
    assert not changed(record, record.model_copy(update={"dirty": True}))
