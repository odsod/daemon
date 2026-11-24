"""Compare user install files before any write or service action."""

from __future__ import annotations

import ast
import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import odsod_daemon
from odsod_daemon.components.install.contract import (
    CAPTURE_ROOTS,
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


def shipped(path: Path) -> bool:
    """Skip what the wheel leaves out, so a source tree and the installed
    package give the same digests."""
    return path.is_file() and not {"__pycache__", "tests", "testdata"} & set(path.parts)


def capture_files(package: Path) -> set[str]:
    """The files under CAPTURE_ROOTS and every package module they import."""

    def module_file(name: str) -> str | None:
        parts = name.split(".")[1:]
        base = package.joinpath(*parts)
        for candidate in (base / "__init__.py", base.with_suffix(".py")):
            if candidate.is_file():
                return candidate.relative_to(package).as_posix()
        return None

    found: set[str] = set()
    todo = [
        path.relative_to(package).as_posix()
        for path in sorted(package.rglob("*"))
        if shipped(path)
        and path.relative_to(package).as_posix().startswith(CAPTURE_ROOTS)
    ]
    while todo:
        name = todo.pop()
        if name in found:
            continue
        found.add(name)
        if not name.endswith(".py"):
            continue
        here = ["odsod_daemon", *Path(name).parent.parts]
        for node in ast.walk(ast.parse((package / name).read_text())):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = here[: len(here) - node.level + 1]
                    base = ".".join([*parent, base] if base else parent)
                modules = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            for module in modules:
                if module.startswith("odsod_daemon"):
                    file = module_file(module)
                    if file:
                        todo.append(file)
    return found


def digests(package: Path) -> dict[str, str]:
    """Hash the installed code: capture's files and the whole package."""
    scope = capture_files(package)
    whole, capture = hashlib.sha256(), hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if not shipped(path):
            continue
        name = path.relative_to(package).as_posix()
        entry = name.encode() + b"\0" + path.read_bytes() + b"\0"
        whole.update(entry)
        if name in scope:
            capture.update(entry)
    return {"all": whole.hexdigest(), "capture": capture.hexdigest()}


class ApplyError(RuntimeError):
    """An install failed at a named step without replacing current."""


def install_user(
    *,
    command: Path,
    candidate: InstallRecord | None = None,
    package: Path | None = None,
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
        source.digests = digests(package or Path(odsod_daemon.__file__).parent)
        old = current.digests if current is not None else {}
        identity_changed = changed(source, current)
        code_changed = source.digests != old
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
        restarted = []
        for service in SERVICES:
            if service == "keys":
                continue
            unit = f"odsod-daemon-{service}.service"
            scope = "capture" if service == "capture" else "all"
            if old.get(scope) != source.digests[scope] or any(
                p.name == unit for p in changes.writes
            ):
                restarted.append(service)
                action = (
                    "restart" if service == "pipeline" or graphical else "try-restart"
                )
                systemd.control(action, unit)
        if "capture" in restarted:
            progress("capture restarted: recording has a gap of about 2 s")
        elif restarted:
            progress(f"restarted {', '.join(restarted)}; capture kept recording")
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
        if identity_changed or code_changed or source.source == "dev":
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
