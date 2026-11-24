"""Pure core of setup: what a server still needs, and how to say it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Step = Literal["adopt", "download-model", "download-source", "build"]


@dataclass(frozen=True)
class Found:
    """What is on disk for one server."""

    model: bool  # in state/models/ with the pinned size
    legacy: bool  # in the machine data dir with the pinned size
    source: bool  # the source tree has its CMakeLists.txt
    binary: bool  # the built server for the pinned version


def steps(found: Found) -> tuple[Step, ...]:
    """The steps that make one server ready, in order."""
    result: list[Step] = []
    if not found.model:
        result.append("adopt" if found.legacy else "download-model")
    if not found.binary:
        if not found.source:
            result.append("download-source")
        result.append("build")
    return tuple(result)


def describe(server: str, found: Found) -> str:
    todo = steps(found)
    model = "present" if found.model else "missing"
    binary = "built" if found.binary else "missing"
    line = f"{server}: model {model}, binary {binary}"
    return line + (f"; to do: {', '.join(todo)}" if todo else "; ready")


def missing_tools(tools: tuple[str, ...], found: set[str]) -> list[str]:
    return [tool for tool in tools if tool not in found]
