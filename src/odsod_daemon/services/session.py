"""The session service: dictation and shortcuts."""

from __future__ import annotations

from odsod_daemon.components import dictation, shortcuts  # noqa: F401
from odsod_daemon.services.runner import ServiceSpec

NAME = "session"

COMPONENTS = [
    # dictation,
    # shortcuts,
]

SERVICE = ServiceSpec(NAME, COMPONENTS)
