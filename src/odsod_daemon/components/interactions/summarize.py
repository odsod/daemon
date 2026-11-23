"""Summary validation and line-based chunks."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

LABELS = ("Decided", "Insight", "Problem", "Context", "Next")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: Literal["Decided", "Insight", "Problem", "Context", "Next"]
    text: str
    owner: str | None


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    skip: bool
    title: str
    overview: str
    points: list[Point]


def validate(reply: str, title_max_words: int = 8) -> Summary:
    value = json.loads(re.sub(r"<think>.*?</think>", "", reply, flags=re.S))
    value["points"] = [
        p
        for p in value["points"]
        if p.get("label") in LABELS and p.get("text", "").strip()
    ]
    summary = Summary.model_validate(value)
    summary.title = " ".join(summary.title.split()[:title_max_words])
    summary.overview = " ".join(re.split(r"(?<=[.!?])\s+", summary.overview)[:3])
    return summary


def chunks(text: str, limit: int) -> list[str]:
    result: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            raise ValueError("one transcript line exceeds chunk_chars")
        if current and len(current) + len(line) > limit:
            result.append(current)
            current = ""
        current += line
    if current:
        result.append(current)
    return result
