"""Pure mic and stall checks, each fault with its ``since`` time."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CAPTURE_STALLED = "capture-stalled"
MIC_SILENT = "mic-silent"
MIC_MUTED = "mic-muted"

WATCHDOG_WINDOW_S = 5.0


@dataclass(frozen=True)
class Active:
    code: str
    since: float
    key: str | None = None


def all_zero(block: bytes) -> bool:
    """True when every sample of a block is exactly zero."""
    return not np.frombuffer(block, dtype="<i2").any()


class MicCheck:
    """Track the mic's zero run and the default source's mute flag."""

    def __init__(self, silent_s: float) -> None:
        self.silent_s = silent_s
        self._zero_since: float | None = None
        self._mute_since: float | None = None

    @property
    def zero_since(self) -> float | None:
        return self._zero_since

    def block(self, block: bytes, start: float) -> None:
        if self._mute_since is not None or not all_zero(block):
            self._zero_since = None
        elif self._zero_since is None:
            self._zero_since = start

    def set_muted(self, muted: bool, now: float) -> None:
        if muted and self._mute_since is None:
            self._mute_since = now
        elif not muted and self._mute_since is not None:
            self._mute_since = None
            self._zero_since = None

    def faults(self, now: float) -> list[Active]:
        active: list[Active] = []
        if self._mute_since is not None:
            active.append(Active(MIC_MUTED, self._mute_since))
        silent = (
            self._zero_since is not None
            and self._mute_since is None
            and now - self._zero_since >= self.silent_s
        )
        if silent:
            active.append(Active(MIC_SILENT, self._zero_since or 0.0))
        return active


def stall_start(audio_end: float | None, service_start: float) -> float:
    """When a channel's current stall began."""
    if audio_end is None:
        return service_start
    return max(audio_end, service_start)


def is_stalled(start: float, now: float, stall_error_s: float) -> bool:
    return now - start >= stall_error_s


def watchdog_ok(
    last_block: dict[str, float | None], now: float, *, window_s: float = 5.0
) -> bool:
    """Both channels wrote a block inside the watchdog window."""
    for channel in ("mic", "sys"):
        seen = last_block.get(channel)
        if seen is None or now - seen > window_s:
            return False
    return True
