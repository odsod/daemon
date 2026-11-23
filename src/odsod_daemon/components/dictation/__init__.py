"""Hold-to-talk dictation, meeting mute and paste.

SUBSYSTEM: dictation
Reads: Keys socket, audio buffer, dictation config.
Writes: utterances/dictation, run/status.json, run/muted.json,
run/health/session.json, clipboard, notifications.
ADR: docs/adr/0013-dictation.md
"""

SUBSYSTEM = "dictation"
