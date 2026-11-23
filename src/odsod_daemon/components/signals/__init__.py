"""Observe meeting tabs over CDP.

SUBSYSTEM: signals
Reads: Chrome DevTools Protocol, signals config.
Writes: events/signals, run/health/pipeline.json.
ADR: docs/adr/0014-signals.md
"""

SUBSYSTEM = "signals"
