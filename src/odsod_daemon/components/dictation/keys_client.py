"""One socket reader routes key events and paste acknowledgements."""

import asyncio
import contextlib

import odsod_daemon.components.keys.contract as contract
from odsod_daemon.lib import clock


class KeysClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.events: asyncio.Queue[contract.MessageTime | None] = asyncio.Queue()
        self.replies: asyncio.Queue[bool] = asyncio.Queue()
        self.pasting = False

    @classmethod
    async def connect(cls, path: str = contract.SOCKET_PATH) -> KeysClient:
        async with clock.timeout(1):
            reader, writer = await asyncio.open_unix_connection(path)
        return cls(reader, writer)

    async def read(self) -> None:
        try:
            while line := await self.reader.readline():
                message = contract.parse(line.decode())
                if isinstance(
                    message, (contract.Start, contract.Stop, contract.Cancel)
                ):
                    self.events.put_nowait(message)
                elif self.pasting and isinstance(
                    message, (contract.Pasted, contract.PasteFailed)
                ):
                    self.replies.put_nowait(isinstance(message, contract.Pasted))
        except OSError, ValueError:
            pass
        finally:
            self.events.put_nowait(None)
            if self.pasting:
                self.replies.put_nowait(False)

    async def paste(self) -> bool:
        # A timed-out response cannot safely be paired with a later request.
        if self.pasting or self.writer.is_closing():
            return False
        self.pasting = True
        try:
            self.writer.write(contract.format(contract.Paste()).encode())
            async with clock.timeout(3):
                await self.writer.drain()
                return await self.replies.get()
        except OSError, TimeoutError:
            self.writer.close()
            return False
        finally:
            self.pasting = False

    async def close(self) -> None:
        self.writer.close()
        with contextlib.suppress(OSError):
            await self.writer.wait_closed()
