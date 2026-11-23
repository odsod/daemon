"""Meeting state machine. Pure: tab candidates and tile counts in, events out.

A candidate tab becomes a meeting only when its page shows a participant
tile. A short loss of tiles waits for ``end_grace_s``. A tab that goes away
or changes its code ends the meeting at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from odsod_daemon.components.signals.platforms.base import MeetingRef

Cause = Literal["left", "tab-closed"]


@dataclass(frozen=True)
class Start:
    ref: MeetingRef
    at: float


@dataclass(frozen=True)
class End:
    ref: MeetingRef
    at: float
    cause: Cause


Event = Start | End


class Meeting:
    def __init__(self, *, end_grace_s: float = 10.0) -> None:
        self._grace = end_grace_s
        self._ref: MeetingRef | None = None
        self._missing_at: float | None = None

    @property
    def active(self) -> MeetingRef | None:
        return self._ref

    def resume(self, ref: MeetingRef) -> None:
        """Adopt a meeting that an earlier process left open."""
        self._ref = ref
        self._missing_at = None

    def observe(
        self, now: float, ref: MeetingRef | None, tiles: int | None
    ) -> list[Event]:
        events: list[Event] = []
        if self._ref is not None:
            if ref is None:
                events.append(End(self._ref, now, "tab-closed"))
                self._end()
                return events
            if ref != self._ref:
                events.append(End(self._ref, now, "tab-closed"))
                self._end()
            elif tiles is None:
                return events
            elif tiles == 0:
                if self._missing_at is None:
                    self._missing_at = now
                if now - self._missing_at >= self._grace:
                    events.append(End(self._ref, self._missing_at, "left"))
                    self._end()
                return events
            else:
                self._missing_at = None

        if self._ref is None and ref is not None and tiles is not None and tiles > 0:
            self._ref = ref
            self._missing_at = None
            events.append(Start(ref, now))
        return events

    def _end(self) -> None:
        self._ref = None
        self._missing_at = None
