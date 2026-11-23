"""Build and install the keys service as root.

ADR-0006 "`odsodctl install --system` (root)". The owner comes from
``SUDO_UID``. Every path takes a prefix, so tests write into a temp root.
"""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from odsod_daemon.components.keys.contract import C_SOURCE_DIR, SYSTEM_UNIT

BINARY_NAME = "odsod-daemon-keys"
BINARY_PATH = Path("usr/local/bin") / BINARY_NAME
UNIT_DIR = Path("etc/systemd/system")
UNIT_PATH = UNIT_DIR / SYSTEM_UNIT
DROPIN_PATH = UNIT_DIR / f"{SYSTEM_UNIT}.d" / "notify.conf"
NOTIFY_UNIT = "odsod-daemon-notify-system@.service"
NOTIFY_PATH = UNIT_DIR / NOTIFY_UNIT
DROPIN_TEMPLATE = "odsod-daemon-keys-notify.conf"
GCC_TIMEOUT_S = 120
SYSTEMCTL_TIMEOUT_S = 120


class SystemError(RuntimeError):
    """The system install cannot run or failed."""


@dataclass(frozen=True)
class SystemInstall:
    binary_changed: bool
    unit_changed: bool
    restarted: bool


def install_system(
    *,
    prefix: Path = Path("/"),
    environ: Mapping[str, str] | None = None,
    odsodctl: Path | None = None,
) -> SystemInstall:
    """Build and install the keys binary, its system unit and the notify unit."""
    env = os.environ if environ is None else environ
    uid, gid, owner = _owner(env)
    command = Path(sys.argv[0]).resolve() if odsodctl is None else odsodctl
    if not command.is_absolute():
        raise SystemError(f"odsodctl path is not absolute: {command}")

    rendered = {
        UNIT_PATH: _render(_keys_template(), uid=uid, gid=gid),
        DROPIN_PATH: _render(_template(DROPIN_TEMPLATE)),
        NOTIFY_PATH: _render(
            _template(NOTIFY_UNIT), owner=owner, uid=uid, odsodctl=command
        ),
    }

    with tempfile.TemporaryDirectory(prefix="odsod-daemon-keys-") as work:
        binary = _build(Path(work))
        binary_changed = _install_file(prefix / BINARY_PATH, binary.read_bytes(), 0o755)

    unit_changed = False
    for path, text in rendered.items():
        unit_changed |= _install_file(prefix / path, text.encode(), 0o644)

    changed = binary_changed or unit_changed
    if changed:
        _systemctl("daemon-reload")
    _systemctl("enable", SYSTEM_UNIT)
    restarted = False
    if changed:
        _systemctl("restart", SYSTEM_UNIT)
        restarted = True
    return SystemInstall(binary_changed, unit_changed, restarted)


def _owner(env: Mapping[str, str]) -> tuple[int, int, str]:
    text = env.get("SUDO_UID", "").strip()
    if not text:
        raise SystemError("SUDO_UID is not set; run `sudo odsodctl install --system`")
    try:
        uid = int(text)
    except ValueError as error:
        raise SystemError(f"SUDO_UID is not a number: {text!r}") from error
    try:
        entry = pwd.getpwuid(uid)
    except KeyError as error:
        raise SystemError(f"SUDO_UID {uid}: no such user") from error
    owner = env.get("SUDO_USER") or entry.pw_name
    gid_text = env.get("SUDO_GID", "").strip()
    gid = int(gid_text) if gid_text.isdigit() else entry.pw_gid
    return uid, gid, owner


def _build(work: Path) -> Path:
    package = resources.files("odsod_daemon.components.keys")
    with resources.as_file(package.joinpath(C_SOURCE_DIR)) as source:
        copied = work / "c"
        shutil.copytree(Path(str(source)), copied)

    binary = work / BINARY_NAME
    result = subprocess.run(
        [
            "gcc",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o",
            str(binary),
            str(copied / "io.c"),
            str(copied / "state.c"),
        ],
        capture_output=True,
        text=True,
        timeout=GCC_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemError(f"gcc failed: {detail}")
    if not binary.is_file():
        raise SystemError("gcc wrote no binary")
    return binary


def _install_file(path: Path, data: bytes, mode: int) -> bool:
    try:
        if path.read_bytes() == data and path.stat().st_mode & 0o777 == mode:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    temporary.chmod(mode)
    temporary.replace(path)
    return True


def _systemctl(*arguments: str) -> None:
    result = subprocess.run(
        ["systemctl", *arguments],
        capture_output=True,
        text=True,
        timeout=SYSTEMCTL_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemError(f"systemctl {' '.join(arguments)} failed: {detail}")


def _render(text: str, **values: object) -> str:
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def _keys_template() -> str:
    package = resources.files("odsod_daemon.components.keys")
    return package.joinpath(SYSTEM_UNIT).read_text(encoding="utf-8")


def _template(name: str) -> str:
    units = resources.files("odsod_daemon.components.install").joinpath("units")
    return units.joinpath(name).read_text(encoding="utf-8")
