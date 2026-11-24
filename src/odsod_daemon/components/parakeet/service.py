"""Fetch and load the model, and serve it on each listen address."""

from __future__ import annotations

import asyncio
import logging

from odsod_daemon.components.parakeet import endpoint, model
from odsod_daemon.components.segmentation.config import Parakeet, Speech
from odsod_daemon.lib import clock, download, healthfile, paths

log = logging.getLogger(__name__)

CODE = "parakeet-unavailable"
BIND_RETRY_S = 5
BIND_WARN_S = 60
FETCH_RETRY_MAX_S = 600


def health(key: str, message: str | None) -> None:
    file = healthfile.HealthFile(paths.roots().run / "health/pipeline.json", "pipeline")
    if message is None:
        file.clear(CODE, key=key)
    else:
        file.set(CODE, message, key=key)
    file.rewrite()


async def listen(address: str, port: int, transcribe: endpoint.Transcribe) -> None:
    """Bind, retrying until the address is up, then serve until cancelled."""
    began = clock.monotonic()
    warned = False
    while True:
        try:
            server = await asyncio.start_server(
                endpoint.handler(transcribe), address, port
            )
        except OSError as error:
            if not warned and clock.monotonic() - began >= BIND_WARN_S:
                health(
                    f"listen-{address}", f"cannot listen on {address}:{port}: {error}"
                )
                warned = True
            await clock.sleep(BIND_RETRY_S)
            continue
        if warned:
            health(f"listen-{address}", None)
        log.info("parakeet: listening on %s:%d", address, port)
        async with server:
            await server.serve_forever()


async def prepare(settings: Parakeet, recognizer: model.Recognizer) -> None:
    directory = paths.roots().state / "models" / model.NAME
    delay = 5.0
    while True:
        try:
            await download.fetch(directory, model.PINS)
            break
        except download.DownloadError as error:
            health("model", f"parakeet model: {error}")
            await clock.sleep(delay)
            delay = min(delay * 2, FETCH_RETRY_MAX_S)
    health("model", None)
    await recognizer.load(directory, settings.threads)
    log.info("parakeet: model loaded")


async def run(speech: Speech, *, once: bool = False) -> None:
    settings = speech.parakeet
    if once:
        return
    if not settings.enabled:
        await asyncio.Event().wait()
    recognizer = model.Recognizer()
    async with asyncio.TaskGroup() as group:
        for address in settings.listen:
            group.create_task(listen(address, settings.port, recognizer))
        await prepare(settings, recognizer)
