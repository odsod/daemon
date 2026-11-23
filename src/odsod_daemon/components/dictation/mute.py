"""Record mutes before changing streams; restore only the same app."""

import asyncio
from pathlib import Path

from odsod_daemon.components.capture.contract import CAPTURE_APP_NAME
from odsod_daemon.components.dictation import pactl
from odsod_daemon.components.dictation.config import MUTE_TIMEOUT
from odsod_daemon.components.dictation.contract import MutedDocument, MutedStream
from odsod_daemon.lib import documents


def read(path: Path) -> MutedDocument:
    return (
        MutedDocument.model_validate(documents.read_json(path))
        if path.exists()
        else MutedDocument()
    )


async def restore(record: MutedDocument) -> None:
    await pactl.unmute([(s.id, s.app) for s in record.streams])


class Mute:
    def __init__(self, path: Path):
        self.path = path
        self.count = 0

    async def start(self) -> bool:
        try:
            async with asyncio.timeout(MUTE_TIMEOUT):
                selected = [
                    MutedStream(id=s.id, app=s.app)
                    for s in await pactl.outputs()
                    if not s.monitor and not s.muted and s.app != CAPTURE_APP_NAME
                ]
                documents.write_json(
                    self.path, MutedDocument(streams=selected).model_dump()
                )
                self.count = len(selected)
                results = await asyncio.gather(
                    *(pactl.set_mute(s.id, True) for s in selected),
                    return_exceptions=True,
                )
                return not any(isinstance(r, BaseException) for r in results)
        except OSError, TimeoutError, ValueError:
            return False

    async def stop(self) -> None:
        await restore(read(self.path))
        documents.write_json(self.path, MutedDocument().model_dump())
