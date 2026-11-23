"""Save and restore both selections around one acknowledged paste."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from odsod_daemon.components.dictation import notify
from odsod_daemon.components.dictation.pactl import command
from odsod_daemon.lib import clock

TEXT = "text/plain;charset=utf-8"
LIMIT = 10 * 1024 * 1024


@dataclass
class Selection:
    mime: str
    data: bytes


async def save(primary: bool) -> Selection | None:
    flags = ["--primary"] if primary else []
    try:
        types = (
            (await command("wl-paste", *flags, "--list-types")).decode().splitlines()
        )
    except OSError as error:
        if str(error).strip().lower() in {"no selection", "nothing is copied"}:
            return Selection(TEXT, b"")
        raise
    if not types:
        return Selection(TEXT, b"")
    mime = TEXT if TEXT in types else types[0]
    data = await command("wl-paste", *flags, "--no-newline", "--type", mime)
    return Selection(mime, data) if len(data) <= LIMIT else None


async def copy(primary: bool, selection: Selection) -> None:
    flags = ["--primary"] if primary else []
    if not selection.data:
        await command("wl-copy", *flags, "--clear")
    else:
        await command(
            "wl-copy",
            *flags,
            "--sensitive",
            "--type",
            selection.mime,
            data=selection.data,
        )


async def paste(
    text: str, request: Callable[[], Awaitable[bool]], delay_ms: int
) -> bool:
    dictated = Selection(TEXT, text.encode())
    try:
        saved = [await save(primary) for primary in (False, True)]
        for primary in (False, True):
            await copy(primary, dictated)
    except OSError, TimeoutError:
        await notify.send("dictation failed")
        return False
    if not await request():
        await notify.send("paste failed: the text is on the clipboard")
        return False
    await clock.sleep(delay_ms / 1000)
    for primary, original in zip((False, True), saved, strict=True):
        if original is None:
            continue
        try:
            current = await save(primary)
            if current == dictated:
                await copy(primary, original)
        except OSError, TimeoutError:
            await notify.send("dictation failed")
    return True
