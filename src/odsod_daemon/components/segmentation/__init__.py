"""Cut audio into utterances and write coverage.

SUBSYSTEM: speech
Reads: Audio buffer, speech config, run/status.json.
Writes: utterances/ambient, coverage, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

from odsod_daemon.components.segmentation.config import Speech as CONFIG_MODEL
from odsod_daemon.components.segmentation.runner import run

SUBSYSTEM = "speech"

__all__ = ["CONFIG_MODEL", "run"]
