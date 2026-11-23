from __future__ import annotations

from pathlib import Path

from odsod_daemon.lib import documents, healthfile


def test_set_and_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "run" / "health" / "capture.json"
    health = healthfile.HealthFile(path, "capture")
    health.set(
        "capture-stalled",
        "No audio for 10 s",
        fix="systemctl --user restart odsod-daemon-capture",
    )
    document = health.rewrite()
    assert document.service == "capture"
    assert document.faults[0].code == "capture-stalled"
    assert document.faults[0].key is None
    assert documents.read_json(path)["faults"][0]["code"] == "capture-stalled"


def test_set_keeps_since(tmp_path: Path) -> None:
    health = healthfile.HealthFile(tmp_path / "health.json", "pipeline")
    first = health.set("inference-unreachable", "down", key="whisper")
    second = health.set("inference-unreachable", "still down", key="whisper")
    assert second.since == first.since
    assert second.message == "still down"


def test_keys_are_independent(tmp_path: Path) -> None:
    health = healthfile.HealthFile(tmp_path / "health.json", "pipeline")
    health.set("inference-unreachable", "down", key="whisper")
    health.set("inference-unreachable", "down", key="llama")
    assert health.clear("inference-unreachable", key="whisper")
    assert [fault.key for fault in health.faults] == ["llama"]


def test_loads_existing_faults(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    first = healthfile.HealthFile(path, "session")
    first.set("keys-socket-missing", "no socket")
    first.rewrite()
    second = healthfile.HealthFile(path, "session")
    assert [fault.code for fault in second.faults] == ["keys-socket-missing"]


def test_clear_missing_returns_false(tmp_path: Path) -> None:
    health = healthfile.HealthFile(tmp_path / "health.json", "session")
    assert health.clear("mute-failed") is False


def test_unreadable_file_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text("not json", encoding="utf-8")
    health = healthfile.HealthFile(path, "tray")
    assert health.faults == []


def test_two_writers_keep_each_others_faults(tmp_path):
    """ADR-0010: clearing one key never clears another, across writers."""
    path = tmp_path / "pipeline.json"
    cached = healthfile.HealthFile(path, "pipeline")
    other = healthfile.HealthFile(path, "pipeline")
    other.set("inference-unreachable", "down", key="whisper")
    other.rewrite()
    cached.set("target-missing", "gone", key="vault")
    cached.set("target-missing", "gone", key="nas")
    cached.rewrite()
    codes = {(f["code"], f["key"]) for f in documents.read_json(path)["faults"]}
    assert codes == {
        ("inference-unreachable", "whisper"),
        ("target-missing", "vault"),
        ("target-missing", "nas"),
    }
    assert cached.clear("target-missing", key="vault")
    cached.rewrite()
    codes = {(f["code"], f["key"]) for f in documents.read_json(path)["faults"]}
    assert codes == {("inference-unreachable", "whisper"), ("target-missing", "nas")}


def test_clear_of_an_absent_fault_leaves_no_tombstone(tmp_path):
    path = tmp_path / "pipeline.json"
    a = healthfile.HealthFile(path, "pipeline")
    b = healthfile.HealthFile(path, "pipeline")
    assert not a.clear("code", key="k")
    b.set("code", "set by b", key="k")
    b.rewrite()
    a.set("other", "set by a")
    a.rewrite()
    codes = {f["code"] for f in documents.read_json(path)["faults"]}
    assert codes == {"code", "other"}
