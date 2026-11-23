"""Record mic and system audio into the hourly buffer.

SUBSYSTEM: capture
Reads: PipeWire, common config.
Writes: Audio buffer, events/capture, run/health/capture.json.
ADR: docs/adr/0011-capture.md
"""

SUBSYSTEM = "capture"
