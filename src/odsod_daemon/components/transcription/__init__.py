"""Run whisper on each utterance.

SUBSYSTEM: speech
Reads: utterances/ambient, utterances/dictation, audio, speech config.
Writes: asr/<backend>, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

from odsod_daemon.components.segmentation.config import Speech as CONFIG_MODEL
from odsod_daemon.components.transcription.worker import run

SUBSYSTEM = "speech"

__all__ = ["CONFIG_MODEL", "run"]
