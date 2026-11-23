"""Models of what the transcript component writes.

The daily transcript is Markdown; this module holds its finished record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

DOCUMENT_TYPE = "transcripts"


class FinishedTranscript(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    kind: Literal["finished"] = "finished"
    document: str
    type: Literal["transcripts"] = DOCUMENT_TYPE
    day: str
    capped: bool = False
