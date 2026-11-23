"""Pure streaming hysteresis cutter. Times are seconds from a fixed origin."""

from dataclasses import dataclass

from odsod_daemon.components.segmentation.config import Settings


@dataclass(frozen=True)
class Cut:
    start: float
    end: float
    vad: float
    reason: str


class Cutter:
    def __init__(self, settings: Settings, floor: float = 0):
        self.settings = settings
        self.floor = floor
        self.frames: list[tuple[float, float, float]] = []
        self.quiet: float | None = None

    @property
    def safe_end(self) -> float:
        if self.frames:
            return max(
                self.floor, self.frames[0][0] - self.settings.pad_start_ms / 1000
            )
        return self.floor

    def _cut(self, end: float, reason: str) -> Cut | None:
        if not self.frames:
            return None
        start = self.frames[0][0]
        selected = [f for f in self.frames if f[0] < end]
        result = None
        if end - start >= self.settings.min_speech_ms / 1000 and selected:
            result = Cut(
                max(self.floor, start - self.settings.pad_start_ms / 1000),
                end,
                round(sum(f[2] for f in selected) / len(selected), 2),
                reason,
            )
        self.frames = []
        self.quiet = None
        self.floor = end
        return result

    def boundary(self, end: float, reason: str) -> list[Cut]:
        result = self._cut(end, reason)
        self.floor = end
        return [result] if result else []

    def feed(self, start: float, end: float, probability: float) -> list[Cut]:
        s = self.settings
        if not self.frames and probability < s.threshold:
            # Keep enough history for the next start pad.
            self.floor = max(self.floor, end - s.pad_start_ms / 1000)
            return []
        self.frames.append((start, end, probability))
        if probability >= s.threshold:
            self.quiet = None
        elif probability < s.neg_threshold and self.quiet is None:
            self.quiet = start
        if self.quiet is not None and end - self.quiet >= s.min_silence_ms / 1000:
            stop = min(end, self.quiet + s.pad_end_ms / 1000)
            # Minimum speech length excludes the trailing silence and pad.
            speech_end = self.quiet
            if speech_end - self.frames[0][0] < s.min_speech_ms / 1000:
                self.frames = []
                self.quiet = None
                self.floor = stop
                return []
            cut = self._cut(stop, "pause")
            return [cut] if cut else []
        if end - self.frames[0][0] >= s.max_s:
            midpoint = self.frames[0][0] + s.max_s / 2
            split = min(
                (f for f in self.frames if f[0] >= midpoint), key=lambda f: f[2]
            )[0]
            tail = [f for f in self.frames if f[0] >= split]
            cut = self._cut(split, "forced")
            self.frames = tail
            self.quiet = None
            return [cut] if cut else []
        return []
