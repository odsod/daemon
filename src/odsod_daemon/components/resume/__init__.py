"""Remove the pause flag, write the resume record and start capture.

SUBSYSTEM: control
Reads: systemd user manager.
Writes: events/user resume; removes run/paused.
ADR: docs/adr/0018-control.md
"""

SUBSYSTEM = "control"
