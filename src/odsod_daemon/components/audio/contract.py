"""Models of what the audio component reads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Clip(BaseModel):
    """The time range of one utterance on one channel."""

    id: str
    channel: str
    start: datetime
    end: datetime
