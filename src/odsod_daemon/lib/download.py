"""Download pinned files: stream, check the SHA-256, rename into place.

A file that is present with its pinned size counts as done: the hash was
checked before the rename, and the size catches truncation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx

CHUNK = 1 << 20


@dataclass(frozen=True)
class Pin:
    name: str
    url: str
    sha256: str
    size: int


class DownloadError(RuntimeError):
    """A file failed to download or does not match its pin."""


def present(directory: Path, pin: Pin) -> bool:
    target = directory / pin.name
    return target.is_file() and target.stat().st_size == pin.size


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


async def fetch(directory: Path, pins: Iterable[Pin]) -> list[str]:
    """Download each missing file. Return the names it downloaded."""
    directory.mkdir(parents=True, exist_ok=True)
    fetched = []
    timeout = httpx.Timeout(60)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        for pin in pins:
            if present(directory, pin):
                continue
            partial = directory / f"{pin.name}.part"
            digest = hashlib.sha256()
            try:
                async with client.stream("GET", pin.url) as response:
                    response.raise_for_status()
                    with partial.open("wb") as out:
                        async for chunk in response.aiter_bytes(CHUNK):
                            digest.update(chunk)
                            out.write(chunk)
            except httpx.HTTPError as error:
                partial.unlink(missing_ok=True)
                raise DownloadError(f"{pin.name}: {error}") from error
            if digest.hexdigest() != pin.sha256:
                partial.unlink(missing_ok=True)
                raise DownloadError(f"{pin.name}: SHA-256 does not match the pin")
            partial.replace(directory / pin.name)
            fetched.append(pin.name)
    return fetched
