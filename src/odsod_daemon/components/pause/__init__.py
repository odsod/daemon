"""Write the pause flag, the pause record and stop capture.

SUBSYSTEM: control
Reads: systemd user manager.
Writes: run/paused, events/user pause.
ADR: docs/adr/0018-control.md
"""

SUBSYSTEM = "control"
