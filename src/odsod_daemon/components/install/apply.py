"""Compare user install files before any write or service action."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from odsod_daemon.components.install.contract import (
    SERVICES,
    InstallRecord,
    PreviousCommit,
)
from odsod_daemon.components.install.render import DBUS, render, unit_directory
from odsod_daemon.components.install.source import candidate as read_candidate
from odsod_daemon.lib import clock, documents, paths, systemd


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


class ApplyError(RuntimeError):
    """An install failed at a named step without replacing current."""


def install_user(
    *,
    command: Path,
    candidate: InstallRecord | None = None,
    progress: Callable[[str], None] = print,
) -> None:
    roots = paths.roots()
    current_path = roots.state / "install/current"
    step, name = 1, "Source"
    source: InstallRecord | None = candidate
    try:
        progress("[1/7] Source")
        source = source or read_candidate()
        current = (
            InstallRecord.model_validate(documents.read_json(current_path))
            if current_path.exists()
            else None
        )
        identity_changed = changed(source, current)
        step, name = 2, "Render"
        progress("[2/7] Render")
        files = render(command)
        home = Path(os.environ["HOME"])
        data = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share")))
        changes = compare(
            files, unit_directory(os.environ), data / "dbus-1/services" / DBUS
        )
        step, name = 3, "Write"
        progress("[3/7] Write")
        for path, text in changes.writes.items():
            documents.write(path, text)
        for path in changes.removals:
            path.unlink()
        step, name = 4, "Reload"
        progress("[4/7] Reload")
        if changes.units_changed:
            systemd.control("daemon-reload")
        step, name = 5, "Enable"
        progress("[5/7] Enable")
        for path, text in files.items():
            if "[Install]" in text:
                systemd.control("enable", path.name)
        step, name = 6, "Restart"
        progress("[6/7] Restart")
        graphical = systemd.control(
            "is-active", "graphical-session.target", check=False
        )
        restart_all = identity_changed or source.source == "dev"
        for service in SERVICES:
            if service == "keys":
                continue
            unit = f"odsod-daemon-{service}.service"
            if restart_all or any(p.name == unit for p in changes.writes):
                action = (
                    "restart" if service == "pipeline" or graphical else "try-restart"
                )
                systemd.control(action, unit)
        systemd.control("start", "odsod-daemon.target")
        if graphical:
            for service in SERVICES:
                if service in ("capture", "session", "tray"):
                    systemd.control("start", f"odsod-daemon-{service}.service")
        step, name = 7, "Record"
        progress("[7/7] Record")
        if current is not None and current.commit != source.commit:
            previous = PreviousCommit(
                commit=current.commit, source=current.source, replaced_at=clock.iso()
            )
            documents.write_json(
                roots.state / "install/previous-commit", previous.model_dump()
            )
        if identity_changed or source.source == "dev":
            documents.write_json(current_path, source.model_dump())
    except Exception as error:
        rerun = (
            "mise run deploy"
            if source is None or source.source == "dev"
            else "mise run daemon:setup"
        )
        raise ApplyError(
            f"failed at step {step} ({name}): {error}\nRerun: {rerun}"
        ) from error
