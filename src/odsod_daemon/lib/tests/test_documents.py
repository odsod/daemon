from __future__ import annotations

from pathlib import Path

import pytest

from odsod_daemon.lib import documents


def test_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "file.txt"
    documents.write(path, "hello\n")
    assert documents.read(path) == "hello\n"


def test_write_leaves_no_temp_name(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    documents.write(path, b"bytes")
    assert [entry.name for entry in tmp_path.iterdir()] == ["file.txt"]


def test_write_replaces_old_content(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    documents.write(path, "old and long")
    documents.write(path, "new")
    assert documents.read(path) == "new"


def test_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "file.json"
    documents.write_json(path, {"b": 2, "a": 1})
    assert documents.read_json(path) == {"a": 1, "b": 2}
    assert documents.read(path).endswith("\n")


def test_remove_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    documents.remove(path)
    documents.write(path, "x")
    documents.remove(path)
    assert not path.exists()
    documents.remove(path)


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        documents.read(tmp_path / "missing")
