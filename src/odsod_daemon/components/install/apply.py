"""Compare user install files before any write or service action."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from odsod_daemon.components.install.contract import InstallRecord


@dataclass(frozen=True)
class Changes:
    writes: dict[Path, str]
    removals: tuple[Path, ...]

    @property
    def units_changed(self) -> bool:
        return bool(self.writes or self.removals)


def compare(rendered: dict[Path, str], unit_dir: Path, dbus_file: Path) -> Changes:
    writes = {}
    for path, text in rendered.items():
        if not path.exists() or path.read_text() != text:
            writes[path] = text
    stale = {
        path
        for path in unit_dir.glob("odsod-daemon-*")
        if path.is_file() and path not in rendered
    }
    if dbus_file.exists() and dbus_file not in rendered:
        stale.add(dbus_file)
    return Changes(writes, tuple(sorted(stale)))


def changed(candidate: InstallRecord, current: InstallRecord | None) -> bool:
    return current is None or (candidate.source, candidate.commit) != (
        current.source,
        current.commit,
    )
