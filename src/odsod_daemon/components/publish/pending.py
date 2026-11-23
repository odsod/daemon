"""Finished documents that a target still needs (pure).

A target gets every finished document of its types, finished at or after the
target first appeared, with no delivery record for the document. There is no
pending window: finished text never expires while its source exists.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from odsod_daemon.components.publish.config import DocumentType


@dataclass(frozen=True)
class Finished:
    document: str
    type: DocumentType
    at: datetime
    path: Path


def pending(
    finished: Iterable[Finished],
    delivered: Iterable[str],
    *,
    since: datetime,
    types: Collection[str],
) -> list[Finished]:
    """The target's missing documents, oldest first, one item per document."""
    done = set(delivered)
    chosen: dict[str, Finished] = {}
    for item in finished:
        if item.type not in types or item.document in done:
            continue
        if item.at < since:
            continue
        current = chosen.get(item.document)
        if current is None or (item.at, item.document) < (current.at, current.document):
            chosen[item.document] = item
    return sorted(chosen.values(), key=lambda item: (item.at, item.document))
