"""The owner's glossary: terms, what they are, and how they get misheard.

``config/glossary.yaml`` is a list of entries, most important last
(ADR-0021). An entry has ``term`` and may have ``note`` and ``heard_as``.
Other keys are kept for agents and tools; the daemon ignores them.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from odsod_daemon.lib import paths

log = logging.getLogger(__name__)

FILE = "glossary.yaml"


class Entry(BaseModel):
    model_config = ConfigDict(extra="allow")

    term: str
    note: str | None = None
    heard_as: list[str] = []


def path(roots: paths.Roots | None = None) -> Path | None:
    """The glossary file, or None when the owner has none."""
    found = (roots or paths.roots()).config / FILE
    return found if found.exists() else None


def load(roots: paths.Roots | None = None) -> list[Entry]:
    """Read the glossary. Raise ValueError on a bad YAML file."""
    found = path(roots)
    if found is None:
        return []
    try:
        raw = yaml.safe_load(found.read_text()) or []
        if not isinstance(raw, list):
            raise ValueError("glossary.yaml must be a list of entries")
        return [Entry.model_validate(item) for item in raw]
    except (yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"bad glossary.yaml: {error}") from error


def current(roots: paths.Roots | None = None) -> list[Entry]:
    """Read the glossary for a service. A bad file logs and gives none, so
    speech keeps running; ``odsodctl config check`` reports the error."""
    try:
        return load(roots)
    except ValueError as error:
        log.warning("%s; using no glossary", error)
        return []


def terms(entries: list[Entry]) -> list[str]:
    return [entry.term for entry in entries]


def _found(word: str, text: str) -> bool:
    return (
        re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None
    )


def relevant(entries: list[Entry], text: str) -> list[Entry]:
    """Entries whose term or a misheard form is in the text."""
    return [
        entry
        for entry in entries
        if any(_found(word, text) for word in [entry.term, *entry.heard_as])
    ]


def hints(entries: list[Entry]) -> str:
    """One line per entry, for an LLM prompt."""
    lines = []
    for entry in entries:
        line = f"- {entry.term}"
        if entry.note:
            line += f": {entry.note}"
        if entry.heard_as:
            line += f" (can be misheard as: {', '.join(entry.heard_as)})"
        lines.append(line)
    return "\n".join(lines)
