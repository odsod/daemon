"""Hold-to-talk dictation, meeting mute and paste.

SUBSYSTEM: dictation
Reads: Keys socket, audio buffer, dictation config.
Writes: utterances/dictation, run/status.json, run/muted.json,
run/health/session.json, clipboard, notifications.
ADR: docs/adr/0013-dictation.md
"""

from odsod_daemon.components.dictation.config import DictationConfig

SUBSYSTEM = "dictation"
CONFIG_MODEL = DictationConfig


async def run(config: DictationConfig, *, once: bool = False) -> None:
    from odsod_daemon.components.dictation.service import Session

    await Session(config).run(once=once)
