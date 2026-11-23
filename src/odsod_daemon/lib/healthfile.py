"""Set and clear the faults of one service in its health file.

A fault is one entry per ``(code, key)``. Setting an existing fault keeps its
``since``. The service rewrites the whole file on each change.

Several components of one service share its file. Each change re-reads the
file and replays this writer's own unwritten changes, so one writer never
drops the faults of another (ADR-0010 "Fault codes").
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from odsod_daemon.lib import clock, documents


class Fault(BaseModel):
    code: str
    key: str | None = None
    since: str
    message: str
    fix: str | None = None


class HealthDocument(BaseModel):
    service: str
    ts: str
    faults: list[Fault] = Field(default_factory=list)


class HealthFile:
    """The health file of one service."""

    def __init__(self, path: Path, service: str) -> None:
        self.path = path
        self.service = service
        self._faults: dict[tuple[str, str | None], Fault] = {}
        self._changes: dict[tuple[str, str | None], Fault | None] = {}
        self._refresh()

    def _refresh(self) -> None:
        self._faults = {}
        if self.path.exists():
            try:
                document = HealthDocument.model_validate(documents.read_json(self.path))
            except ValueError, OSError:
                document = None
            for fault in document.faults if document else []:
                self._faults[(fault.code, fault.key)] = fault
        for key, fault in self._changes.items():
            if fault is None:
                self._faults.pop(key, None)
            else:
                self._faults[key] = fault

    def set(
        self,
        code: str,
        message: str,
        *,
        key: str | None = None,
        fix: str | None = None,
        since: str | None = None,
    ) -> Fault:
        self._refresh()
        existing = self._faults.get((code, key))
        fault = Fault(
            code=code,
            key=key,
            since=existing.since if existing else (since or clock.iso()),
            message=message,
            fix=fix,
        )
        self._faults[(code, key)] = fault
        self._changes[(code, key)] = fault
        return fault

    def clear(self, code: str, *, key: str | None = None) -> bool:
        self._refresh()
        if self._faults.pop((code, key), None) is None:
            return False
        self._changes[(code, key)] = None
        return True

    @property
    def faults(self) -> list[Fault]:
        return sorted(
            self._faults.values(), key=lambda fault: (fault.code, fault.key or "")
        )

    def document(self) -> HealthDocument:
        return HealthDocument(
            service=self.service,
            ts=clock.iso(),
            faults=self.faults,
        )

    def rewrite(self) -> HealthDocument:
        self._refresh()
        document = self.document()
        documents.write_json(self.path, document.model_dump(mode="json"))
        self._changes.clear()
        return document

    def rewrite_empty(self) -> HealthDocument:
        """Drop every fault, of every writer, and write the file."""
        self._faults = {}
        self._changes = {}
        document = self.document()
        documents.write_json(self.path, document.model_dump(mode="json"))
        return document
