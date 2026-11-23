"""The four service processes. Composition only."""

from __future__ import annotations

from odsod_daemon.services import capture, pipeline, session, tray
from odsod_daemon.services.runner import ServiceSpec

SERVICES: dict[str, ServiceSpec] = {
    module.NAME: module.SERVICE for module in (capture, pipeline, session, tray)
}
