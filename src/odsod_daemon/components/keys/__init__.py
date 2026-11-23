"""Remap every keyboard, the dictation key and the paste chord.

SUBSYSTEM: keys
Reads: Physical keyboards, the dictation socket (paste).
Writes: Uinput key events, dictation socket messages.
ADR: docs/adr/0007-keys-service.md
"""

SUBSYSTEM = "keys"
