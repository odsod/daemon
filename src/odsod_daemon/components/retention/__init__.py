"""Delete audio older than the retention period.

SUBSYSTEM: capture
Reads: Audio buffer, common config.
Writes: Nothing; it deletes old audio.
ADR: docs/adr/0011-capture.md
"""

SUBSYSTEM = "capture"
