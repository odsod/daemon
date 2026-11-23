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
