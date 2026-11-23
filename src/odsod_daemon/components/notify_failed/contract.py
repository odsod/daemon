"""The desktop notification model.

Both notify-failed and the tray write notifications, so the model lives with
the command that delivers a failed unit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Urgency = Literal["low", "normal", "critical"]


class Notification(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    body: str
    urgency: Urgency = "normal"
