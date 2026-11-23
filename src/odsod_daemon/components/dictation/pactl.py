"""Bounded pactl access. This module keeps crash cleanup light."""

import asyncio
import json
from dataclasses import dataclass


async def command(*args: str, data: bytes | None = None, timeout_s: float = 2) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if data is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(timeout_s):
            out, err = await process.communicate(data)
        if process.returncode:
            raise OSError(err.decode(errors="replace").strip() or args[0])
        return out
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


async def set_mute(stream_id: str, muted: bool) -> None:
    await command("pactl", "set-source-output-mute", stream_id, "1" if muted else "0")
