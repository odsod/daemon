"""Observe meeting tabs over CDP.

SUBSYSTEM: signals
Reads: Chrome DevTools Protocol, signals config.
Writes: events/signals, run/health/pipeline.json.
ADR: docs/adr/0014-signals.md
"""

from __future__ import annotations

import logging

from odsod_daemon.components.signals.collector import Collector
from odsod_daemon.components.signals.config import SignalsConfig

SUBSYSTEM = "signals"
CONFIG_MODEL = SignalsConfig

log = logging.getLogger(__name__)


async def run(config: SignalsConfig, *, once: bool = False) -> None:
    if not config.cdp_ports:
        log.info("no CDP ports configured: signals off")
        return
    await Collector(config).run(once=once)
