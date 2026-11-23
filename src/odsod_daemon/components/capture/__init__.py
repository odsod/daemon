"""Record mic and system audio into the hourly buffer.

SUBSYSTEM: capture
Reads: PipeWire, common config.
Writes: Audio buffer, events/capture, run/health/capture.json.
ADR: docs/adr/0011-capture.md
"""

from __future__ import annotations

from odsod_daemon.components.capture import service
from odsod_daemon.components.capture.config import CaptureConfig

SUBSYSTEM = "capture"
CONFIG_MODEL = CaptureConfig
WATCHDOG_OWNER = True


async def run(config: CaptureConfig, *, once: bool = False) -> None:
    """Run the capture loop until SIGTERM, then write a ``stop`` per channel."""
    await service.run(config, once=once)
