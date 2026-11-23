"""Render one result model as text or JSON."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO

from pydantic import BaseModel


def render[T: BaseModel](model: T, *, as_json: bool, text: Callable[[T], str]) -> str:
    if as_json:
        return model.model_dump_json(indent=2)
    return text(model)


def emit[T: BaseModel](
    model: T,
    *,
    as_json: bool,
    text: Callable[[T], str],
    stream: TextIO | None = None,
) -> None:
    output = sys.stdout if stream is None else stream
    print(render(model, as_json=as_json, text=text), file=output)
