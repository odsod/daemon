"""Unmute streams left muted by a dead session service.

SUBSYSTEM: dictation
Reads: run/muted.json, PipeWire.
Writes: Nothing; it unmutes streams.
ADR: docs/adr/0013-dictation.md
"""

SUBSYSTEM = "dictation"
