"""Scripted keys peer using the real line contract."""

import asyncio
from pathlib import Path

from odsod_daemon.components.keys import contract


class Keys:
    def __init__(self):
        self.writer: asyncio.StreamWriter | None = None
        self.connected = asyncio.Event()
        self.pastes: list[bytes] = []
        self.pasted = asyncio.Event()
        self.reply = True
        self.on_paste = lambda: b""

    async def accept(self, reader, writer):
        self.writer = writer
        self.connected.set()
        try:
            while line := await reader.readline():
                assert contract.parse(line.decode()) == contract.Paste()
                self.pastes.append(self.on_paste())
                writer.write(
                    b"pasted\n" if self.reply else b"paste-failed modifiers-held\n"
                )
                await writer.drain()
                self.pasted.set()
        finally:
            writer.close()
            await writer.wait_closed()
            self.writer = None
            self.connected.clear()

    async def send(self, message: contract.Message):
        assert self.writer is not None
        self.writer.write(contract.format(message).encode())
        await self.writer.drain()

    async def serve(self, path: Path):
        return await asyncio.start_unix_server(self.accept, path=str(path))
