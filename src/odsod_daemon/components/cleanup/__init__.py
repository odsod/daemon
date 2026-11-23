"""Clean ASR text with the local LLM.

SUBSYSTEM: speech
Reads: asr, glossary, prompts, speech config.
Writes: text, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

SUBSYSTEM = "speech"
