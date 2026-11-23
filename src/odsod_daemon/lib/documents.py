"""Whole-file reads and atomic writes.

A document is written to ``.<name>.tmp`` in the same directory and then
renamed into place. Readers ignore temp names.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def temp_name(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def write(path: Path, content: str | bytes) -> None:
    """Write a whole document atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = temp_name(path)
    data = content.encode() if isinstance(content, str) else content
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(read(path))


def remove(path: Path) -> None:
    """Remove a document if it exists."""
    path.unlink(missing_ok=True)
