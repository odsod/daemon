"""Play or export the audio of one utterance, to re-listen to unclear speech.

SUBSYSTEM: capture
Reads: state/utterances/{ambient,dictation}/, state/audio/<channel>/.
Writes: a WAV file (export), or audio to the default output (play).
ADR: docs/adr/0011-capture.md
"""

SUBSYSTEM = "capture"
