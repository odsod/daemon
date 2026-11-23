"""Build one summary document per interaction.

SUBSYSTEM: interactions
Reads: utterances, text, events, coverage, glossary, prompts, interactions config.
Writes: interactions, documents/interactions, finished/interactions,
run/health/pipeline.json.
ADR: docs/adr/0016-interactions.md
"""

SUBSYSTEM = "interactions"
