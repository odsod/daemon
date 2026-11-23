"""Copy finished documents to configured targets.

SUBSYSTEM: publishing
Reads: finished, publishing config.
Writes: published/<target>, target copies, run/health/pipeline.json.
ADR: docs/adr/0017-publishing.md
"""

from odsod_daemon.components.publish.config import (
    PublishingConfig as CONFIG_MODEL,
)
from odsod_daemon.components.publish.service import run

SUBSYSTEM = "publishing"

__all__ = ["CONFIG_MODEL", "run"]
