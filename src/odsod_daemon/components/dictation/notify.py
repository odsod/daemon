"""Desktop notices for failed dictation and paste."""

import contextlib

from odsod_daemon.components.dictation.pactl import command


async def send(message: str) -> None:
    with contextlib.suppress(OSError, TimeoutError):
        await command("notify-send", "Dictation", message)
