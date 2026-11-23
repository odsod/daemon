"""Render only shipped user units and their supporting templates."""

from __future__ import annotations

import os
from collections.abc import Mapping
from importlib import resources
from pathlib import Path

from odsod_daemon.components.install.contract import SERVICES

SUPPORT = (
    "odsod-daemon.target",
    "odsod-daemon-login.service",
    "odsod-daemon-resume.timer",
    "odsod-daemon-resume.service",
    "odsod-daemon-retention.timer",
    "odsod-daemon-retention.service",
    "odsod-daemon-notify@.service",
)
DBUS = "io.github.odsod.daemon.session.service"


def unit_directory(env: Mapping[str, str]) -> Path:
    return (
        Path(env.get("XDG_CONFIG_HOME", str(Path(env["HOME"]) / ".config")))
        / "systemd/user"
    )


def substitute(template: str, values: Mapping[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    if "{{" in template:
        raise ValueError("unresolved template variable")
    return template


def render(command: Path, env: Mapping[str, str] | None = None) -> dict[Path, str]:
    if not command.is_absolute():
        raise ValueError("odsodctl path must be absolute")
    env = os.environ if env is None else env
    directory = unit_directory(env)
    templates = resources.files("odsod_daemon.components.install").joinpath("units")
    # systemd command lines use double-quoted arguments and %% for literal %.
    quoted = (
        '"'
        + str(command)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
        .replace("$", "$$")
        + '"'
    )
    values = {
        "odsodctl": quoted,
        "target_wants": " ".join(
            [
                *[
                    f"odsod-daemon-{name}.service"
                    for name in SERVICES
                    if name == "pipeline"
                ],
                "odsod-daemon-resume.timer",
                "odsod-daemon-retention.timer",
            ]
        ),
    }
    names = (
        *SUPPORT,
        *(f"odsod-daemon-{name}.service" for name in SERVICES if name != "keys"),
    )
    result = {
        directory / name: substitute(templates.joinpath(name).read_text(), values)
        for name in names
    }
    if "session" in SERVICES:
        data = Path(env.get("XDG_DATA_HOME", str(Path(env["HOME"]) / ".local/share")))
        result[data / "dbus-1/services" / DBUS] = substitute(
            templates.joinpath(DBUS).read_text(), values
        )
    return result
