"""Set and clear the faults of one service in its health file.

A fault is one entry per ``(code, key)``. Setting an existing fault keeps its
``since``. The service rewrites the whole file on each change.
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
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = HealthDocument.model_validate(documents.read_json(self.path))
        except ValueError, OSError:
            return
        for fault in document.faults:
            self._faults[(fault.code, fault.key)] = fault

    def set(
        self,
        code: str,
        message: str,
        *,
        key: str | None = None,
        fix: str | None = None,
        since: str | None = None,
    ) -> Fault:
        existing = self._faults.get((code, key))
        fault = Fault(
            code=code,
            key=key,
            since=existing.since if existing else (since or clock.iso()),
            message=message,
            fix=fix,
        )
        self._faults[(code, key)] = fault
        return fault

    def clear(self, code: str, *, key: str | None = None) -> bool:
        return self._faults.pop((code, key), None) is not None

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
        document = self.document()
        documents.write_json(self.path, document.model_dump(mode="json"))
        return document
