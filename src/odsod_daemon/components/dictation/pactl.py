"""Bounded pactl access. This module keeps crash cleanup light."""

import asyncio
import json
from dataclasses import dataclass


async def command(
    *args: str, data: bytes | None = None, timeout_s: float = 2, output: bool = True
) -> bytes:
    """Without output, pipes stay closed: wl-copy forks a child that keeps them."""
    pipe = asyncio.subprocess.PIPE if output else asyncio.subprocess.DEVNULL
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if data is not None else None,
        stdout=pipe,
        stderr=pipe,
    )
    try:
        async with asyncio.timeout(timeout_s):
            out, err = await process.communicate(data)
        if process.returncode:
            message = err.decode(errors="replace").strip() if err else ""
            raise OSError(message or args[0])
        return out or b""
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@dataclass(frozen=True)
class Stream:
    id: str
    app: str
    muted: bool
    monitor: bool


async def outputs() -> list[Stream]:
    sources, outputs = await asyncio.gather(
        command("pactl", "--format=json", "list", "sources"),
        command("pactl", "--format=json", "list", "source-outputs"),
    )
    monitors = {
        str(s["index"])
        for s in json.loads(sources)
        if s.get("monitor_of_sink") not in (None, "", 4294967295, "4294967295")
        or s.get("properties", {}).get("device.class") == "monitor"
        or s.get("name", "").endswith(".monitor")
    }
    return [
        Stream(
            str(s["index"]),
            s.get("properties", {}).get("application.name", ""),
            bool(s.get("mute")),
            str(s["source"]) in monitors,
        )
        for s in json.loads(outputs)
    ]


async def muted_source() -> str | None:
    """The default source's name when it is muted, as a hardware mute key does."""
    name, sources = await asyncio.gather(
        command("pactl", "get-default-source"),
        command("pactl", "--format=json", "list", "sources"),
    )
    default = name.decode().strip()
    for source in json.loads(sources):
        if source.get("name") == default:
            return default if source.get("mute") else None
    return None


async def set_source_mute(name: str, muted: bool) -> None:
    await command("pactl", "set-source-mute", name, "1" if muted else "0")


async def set_mute(stream_id: str, muted: bool) -> None:
    await command("pactl", "set-source-output-mute", stream_id, "1" if muted else "0")


async def unmute(streams: list[tuple[str, str]]) -> None:
    if not streams:
        return
    live = {s.id: s.app for s in await outputs()}
    results = await asyncio.gather(
        *(
            set_mute(stream_id, False)
            for stream_id, app in streams
            if live.get(stream_id) == app
        ),
        return_exceptions=True,
    )
    if any(isinstance(result, BaseException) for result in results):
        raise OSError("could not restore meeting streams")
