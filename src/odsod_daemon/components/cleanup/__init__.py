"""Clean ASR text with the local LLM.

SUBSYSTEM: speech
Reads: asr, glossary, prompts, speech config.
Writes: text, run/health/pipeline.json.
ADR: docs/adr/0012-speech.md
"""

from odsod_daemon.components.segmentation.config import Speech as CONFIG_MODEL

SUBSYSTEM = "speech"


async def run(config: CONFIG_MODEL, *, once: bool = False) -> None:
    from odsod_daemon.components.cleanup.worker import run as worker

    await worker(config, once=once)
