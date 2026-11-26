"""Send a satellite's audio and events to the base.

SUBSYSTEM: sync
Reads: audio, events, utterances/dictation, run/status.json.
Writes: the host root of this host on the base, run/health/pipeline.json,
state/sync-paused (odsodctl sync pause).
ADR: docs/adr/0024-base-and-satellites.md
"""

from odsod_daemon.components.sync.config import SyncConfig as CONFIG_MODEL
from odsod_daemon.components.sync.service import run

SUBSYSTEM = "sync"

__all__ = ["CONFIG_MODEL", "run"]
