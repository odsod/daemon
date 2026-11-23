"""Models and constants for the keys component.

The session service reads the socket messages. install reads the package-data
names.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SOCKET_PATH = "/run/odsod-daemon-keys/dictation.sock"
C_SOURCE_DIR = "c"
SYSTEM_UNIT = "odsod-daemon-keys.service"


class _Message(BaseModel):
    model_config = ConfigDict(extra="allow")


class Start(_Message):
    kind: Literal["start"] = "start"
    time: str


class Stop(_Message):
    kind: Literal["stop"] = "stop"
    time: str


class Cancel(_Message):
    kind: Literal["cancel"] = "cancel"
    time: str


class Paste(_Message):
    kind: Literal["paste"] = "paste"


class Pasted(_Message):
    kind: Literal["pasted"] = "pasted"


class PasteFailed(_Message):
    kind: Literal["paste-failed"] = "paste-failed"
    reason: str


Message = Start | Stop | Cancel | Paste | Pasted | PasteFailed


MessageTime = Start | Stop | Cancel


def parse(text: str) -> Message:
    """Parse one socket message line. A trailing newline is allowed."""
    line = text.rstrip("\r\n")
    kind, _, rest = line.partition(" ")
    if kind == "start":
        return Start(time=_time(line, rest))
    if kind == "stop":
        return Stop(time=_time(line, rest))
    if kind == "cancel":
        return Cancel(time=_time(line, rest))
    if kind == "paste":
        if rest:
            raise ValueError(f"{line!r}: unexpected argument")
        return Paste()
    if kind == "pasted":
        if rest:
            raise ValueError(f"{line!r}: unexpected argument")
        return Pasted()
    if kind == "paste-failed":
        if not rest:
            raise ValueError(f"{line!r}: missing reason")
        return PasteFailed(reason=rest)
    raise ValueError(f"{line!r}: unknown message")


def format(message: Message) -> str:
    """Format one socket message line, with its trailing newline."""
    if isinstance(message, (Start, Stop, Cancel)):
        return f"{message.kind} {message.time}\n"
    if isinstance(message, (Paste, Pasted)):
        return f"{message.kind}\n"
    if not message.reason:
        raise ValueError("paste-failed: missing reason")
    return f"paste-failed {message.reason}\n"


def _time(line: str, rest: str) -> str:
    if not rest or " " in rest:
        raise ValueError(f"{line!r}: bad time")
    return rest
