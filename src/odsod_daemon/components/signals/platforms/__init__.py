"""One platform module per meeting platform."""

from __future__ import annotations

from odsod_daemon.components.signals.platforms.base import Platform
from odsod_daemon.components.signals.platforms.meet import Meet
from odsod_daemon.components.signals.platforms.teams import Teams

PLATFORMS: tuple[Platform, ...] = (Meet(), Teams())
