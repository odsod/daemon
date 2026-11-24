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
    try:
        await pactl.unmute([(s.id, s.app) for s in record.streams])
    finally:
        if record.source:
            await pactl.set_source_mute(record.source, True)


class Mute:
    def __init__(self, path: Path):
        self.path = path
        self.count = 0

    async def start(self) -> bool:
        self.count = 0
        try:
            async with asyncio.timeout(MUTE_TIMEOUT):
                streams, source = await asyncio.gather(
                    pactl.outputs(), pactl.muted_source()
                )
                selected = [
                    MutedStream(id=s.id, app=s.app)
                    for s in streams
                    if not s.monitor and not s.muted and s.app != CAPTURE_APP_NAME
                ]
                # The record names the mic before it is unmuted (ADR-0013).
                documents.write_json(
                    self.path,
                    MutedDocument(streams=selected, source=source).model_dump(),
                )
                self.count = len(selected)
                results = await asyncio.gather(
                    *(pactl.set_mute(s.id, True) for s in selected),
                    return_exceptions=True,
                )
                if any(isinstance(r, BaseException) for r in results):
                    return False
                # Meetings are deaf before the mic opens.
                if source:
                    await pactl.set_source_mute(source, False)
                return True
        except OSError, TimeoutError, ValueError:
            return False

    async def stop(self) -> None:
        try:
            record = read(self.path)
        except ValueError:
            # A corrupt record names no streams; reset it so it fails once.
            documents.write_json(self.path, MutedDocument().model_dump())
            raise
        await restore(record)
        documents.write_json(self.path, MutedDocument().model_dump())
