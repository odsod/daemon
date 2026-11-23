"""Write the live daily transcript and its finish record.

SUBSYSTEM: transcript
Reads: events, utterances, text, coverage, transcript config.
Writes: documents/transcripts, finished/transcript.
ADR: docs/adr/0015-transcript.md
"""

from odsod_daemon.components.transcript.config import TranscriptConfig as CONFIG_MODEL
from odsod_daemon.components.transcript.writer import run

SUBSYSTEM = "transcript"

__all__ = ["CONFIG_MODEL", "run"]
