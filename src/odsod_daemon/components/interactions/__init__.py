"""Build one summary document per interaction.

SUBSYSTEM: interactions
Reads: utterances, text, events, coverage, glossary, prompts, interactions config.
Writes: interactions, documents/interactions, finished/interactions,
run/health/pipeline.json.
ADR: docs/adr/0016-interactions.md
"""

from odsod_daemon.components.interactions.config import (
    InteractionsConfig as CONFIG_MODEL,
)
from odsod_daemon.components.interactions.service import run

SUBSYSTEM = "interactions"

__all__ = ["CONFIG_MODEL", "run"]
