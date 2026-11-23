"""Cut audio into utterances and write coverage.

SUBSYSTEM: speech
Reads: Audio buffer, speech config, run/status.json.
Writes: utterances/ambient, coverage, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

SUBSYSTEM = "speech"
