"""Pure time anchoring: (block, arrival time) to a place to write.

The anchor holds ``t0``, the wall time of the first sample, and the end of
the audio written so far. Each block arrives at its end, so the drift of a
block is its arrival minus its expected end. A median over the last blocks
keeps pipe jitter out. Audio that falls behind the wall clock gets a hole;
audio that runs ahead of it is dropped.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

BLOCK_SECONDS = 0.1
BLOCK_BYTES = 3_200
GAP_THRESHOLD_S = 1.0
HISTORY = 10
REANCHOR_MS = 150.0


@dataclass(frozen=True)
class Placement:
    """Where one block belongs on the wall clock."""

    start: float
    end: float
    hole: float = 0.0
    dropped: bool = False


class Anchor:
    """Map block arrivals to wall-clock write ranges."""

    def __init__(
        self,
        *,
        latency_ms: float = 0.0,
        reanchor_ms: float = REANCHOR_MS,
        block_seconds: float = BLOCK_SECONDS,
        history: int = HISTORY,
    ) -> None:
        self._latency = latency_ms / 1000
        self._reanchor = reanchor_ms / 1000
        self._block = block_seconds
        self._history: deque[float] = deque(maxlen=history)
        self._t0: float | None = None
        self._end = 0.0
        self._dropping = False

    @property
    def t0(self) -> float | None:
        """Wall time of the first sample, once the first block arrived."""
        return self._t0

    def place(self, arrival: float, *, duration: float | None = None) -> Placement:
        duration = self._block if duration is None else duration
        if self._t0 is None:
            self._t0 = arrival - duration - self._latency
            self._end = self._t0 + duration
            return Placement(start=self._t0, end=self._end)

        end = self._end + duration
        drift = arrival - self._latency - end

        if self._dropping:
            if drift < 0:
                return Placement(start=self._end, end=self._end, dropped=True)
            self._dropping = False
            self._history.clear()

        self._history.append(drift)
        smoothed = statistics.median(self._history)

        if smoothed < -self._reanchor:
            self._dropping = True
            self._history.clear()
            return Placement(start=self._end, end=self._end, dropped=True)

        if smoothed > self._reanchor:
            start = arrival - self._latency - duration
            hole = max(0.0, start - self._end)
            self._end = arrival - self._latency
            self._history.clear()
            return Placement(start=start, end=self._end, hole=hole)

        start = self._end
        self._end = end
        return Placement(start=start, end=end)
