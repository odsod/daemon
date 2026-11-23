"""Evaluate the daemon state from files and units.

SUBSYSTEM: control
Reads: Health files, status, pause flag, install record, audio, text, coverage, systemd.
Writes: Nothing; it has no run and no command.
ADR: docs/adr/0018-control.md
"""

SUBSYSTEM = "control"
