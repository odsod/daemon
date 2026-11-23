"""The tray service: the tray component of control."""

from __future__ import annotations

from odsod_daemon.components import tray  # noqa: F401
from odsod_daemon.services.runner import ServiceSpec

NAME = "tray"

COMPONENTS = [
    # tray,
]

SERVICE = ServiceSpec(NAME, COMPONENTS)
