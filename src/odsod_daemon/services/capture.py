"""The capture service: the capture component alone."""

from __future__ import annotations

from odsod_daemon.components import capture  # noqa: F401
from odsod_daemon.services.runner import ServiceSpec

NAME = "capture"

COMPONENTS = [
    # capture,
]

SERVICE = ServiceSpec(NAME, COMPONENTS)
