"""Serve Parakeet speech-to-text on CPU for dictation, on the inference host.

SUBSYSTEM: speech
Reads: speech config, state/models/parakeet-tdt-0.6b-v2.
Writes: state/models/parakeet-tdt-0.6b-v2, run/health/pipeline.json.
ADR: docs/adr/0022-dictation-asr.md
"""

from odsod_daemon.components.parakeet.service import run
from odsod_daemon.components.segmentation.config import Speech as CONFIG_MODEL

SUBSYSTEM = "speech"

__all__ = ["CONFIG_MODEL", "run"]
