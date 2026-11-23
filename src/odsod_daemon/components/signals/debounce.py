"""Speaker debounce. Pure: poll samples in, speaker changes out.

A speaker starts after enough samples in a short window, so a one-poll flash
never counts. A speaker stops after a grace period with no sample.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Change:
    name: str
    active: bool
    at: float


@dataclass
class _State:
    samples: list[float] = field(default_factory=list)
    last_seen: float | None = None
    active: bool = False

    def trim(self, cutoff: float) -> None:
        self.samples = [sample for sample in self.samples if sample >= cutoff]


class SpeakerDebounce:
    def __init__(
        self,
        *,
        start_samples: int = 2,
        start_window_s: float = 1.5,
        stop_grace_s: float = 2.0,
        poll_s: float = 0.25,
    ) -> None:
        self._start_samples = start_samples
        self._start_window_s = start_window_s
        self._stop_grace_s = stop_grace_s
        self._poll_s = poll_s
        self._states: dict[str, _State] = {}

    @property
    def active(self) -> frozenset[str]:
        return frozenset(name for name, state in self._states.items() if state.active)

    def resume(self, names: Iterable[str], at: float) -> None:
        """Adopt speakers that a previous process saw as active."""
        for name in names:
            state = self._state(name)
            state.active = True
            state.samples = []
            state.last_seen = at

    def reset(self) -> None:
        self._states = {}

    def observe(self, at: float, speaking: Iterable[str]) -> list[Change]:
        seen = {name for name in speaking if name}
        cutoff = at - self._start_window_s

        for name in seen:
            state = self._state(name)
            state.trim(cutoff)
            state.samples.append(at)
            state.last_seen = at
        for name, state in self._states.items():
            if name not in seen:
                state.trim(cutoff)

        changes: list[Change] = []
        for name in sorted(self._states):
            state = self._states[name]
            if not state.active and len(state.samples) >= self._start_samples:
                state.active = True
                changes.append(Change(name, True, state.samples[0]))
                continue
            if (
                state.active
                and state.last_seen is not None
                and at - state.last_seen > self._stop_grace_s
            ):
                state.active = False
                changes.append(Change(name, False, state.last_seen + self._poll_s))
                state.samples = []
        return changes

    def _state(self, name: str) -> _State:
        state = self._states.get(name)
        if state is None:
            state = _State()
            self._states[name] = state
        return state
