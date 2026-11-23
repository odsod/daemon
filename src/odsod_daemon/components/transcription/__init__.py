"""Run whisper on each utterance.

SUBSYSTEM: speech
Reads: utterances/ambient, utterances/dictation, audio, speech config.
Writes: asr/<backend>, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

SUBSYSTEM = "speech"
