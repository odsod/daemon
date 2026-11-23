"""Pure hold state machine. The shell runs returned actions in order."""

from dataclasses import dataclass
from typing import Literal

from odsod_daemon.components.dictation.config import MAX_HOLD, POSTROLL, PREROLL

Action = Literal["mute", "dictating", "unmute", "cover", "append", "idle", "queue"]


@dataclass
class Loop:
    state: str = "offline"
    press: float = 0
    release: float = 0

    @property
    def start(self) -> float:
        return self.press - PREROLL

    @property
    def end(self) -> float:
        return self.release + POSTROLL

    def event(self, kind: str, at: float = 0) -> list[Action]:
        if kind == "connected" and self.state == "offline":
            self.state = "idle"
        elif kind == "start" and self.state == "idle":
            self.press = at
            self.state = "dictating"
            return ["mute", "dictating"]
        elif self.state == "dictating":
            if kind == "stop" or (kind == "tick" and at >= self.press + MAX_HOLD):
                self.release = min(at, self.press + MAX_HOLD)
                self.state = "closing"
                return ["unmute", "cover"]
            if kind in {"cancel", "disconnected"}:
                self.state = "offline" if kind == "disconnected" else "idle"
                return ["unmute", "idle"]
        elif self.state == "closing" and kind in {"covered", "failed"}:
            self.state = "idle"
            return ["append", "idle", "queue"] if kind == "covered" else ["idle"]
        if kind == "disconnected":
            self.state = "offline"
        return []
