"""Evaluate health off the Qt thread and follow run/status.json."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import watchfiles

from odsod_daemon.components.health.backlog import BacklogTracker
from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import (
    Backlog,
    DictationState,
    Reason,
    StatusReport,
)
from odsod_daemon.components.health.evaluate import evaluate
from odsod_daemon.components.health.snapshot import Snapshot, gather
from odsod_daemon.components.notify_failed.contract import Notification
from odsod_daemon.components.notify_failed.notify import send
from odsod_daemon.lib import clock, config, documents, paths, systemd

MODES = ("idle", "dictating")
KEYS = ("connected", "paused", "no-inference", "no-socket")


class TrayWorker:
    def __init__(
        self,
        roots: paths.Roots,
        source: systemd.UnitStateSource,
        settings: ControlConfig,
        *,
        report: Callable[[StatusReport], None],
        notify: Callable[[Notification], bool] = send,
        tracker: BacklogTracker | None = None,
        debounce_ms: int = 20,
    ) -> None:
        self.roots = roots
        self.source = source
        self.settings = settings
        self.report = report
        self.notify = notify
        if tracker is None:
            common = config.load_common(roots)
            tracker = BacklogTracker(roots.state, common.retention_days)
        self.tracker = tracker
        self.debounce_ms = debounce_ms
        self.following = threading.Event()
        self._errors: set[tuple[str, str]] = set()
        self._snapshot: Snapshot | None = None
        self._stop = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def evaluate_once(self) -> None:
        now = clock.utc_now()
        self.tracker.update(now)
        self._snapshot = await gather(
            self.roots,
            self.source,
            now=now,
            tracker=self.tracker,
            settings=self.settings,
        )
        self._publish()

    def notify_new(self, report: StatusReport) -> None:
        causes = {
            (reason.code, reason.service)
            for reason in report.reasons
            if reason.severity == "error" and reason.code != "unit-failed"
        }
        for code, service in sorted(causes - self._errors):
            reason = next(
                item
                for item in report.reasons
                if (item.code, item.service) == (code, service)
            )
            self.notify(
                Notification(
                    title=f"odsod-daemon: {service}",
                    body=_body(reason),
                    urgency="critical",
                )
            )
        self._errors = causes

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        try:
            await self._safe_evaluate()
            tasks = [
                asyncio.create_task(self._tick()),
                asyncio.create_task(self._follow()),
            ]
            stopper = asyncio.create_task(self._stop.wait())
            try:
                await asyncio.wait(
                    [*tasks, stopper], return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                for task in (*tasks, stopper):
                    task.cancel()
                await asyncio.gather(*tasks, stopper, return_exceptions=True)
        finally:
            close = getattr(self.source, "close", None)
            if close is not None:
                await close()

    def stop(self) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            self._stop.set()
            return
        loop.call_soon_threadsafe(self._stop.set)

    async def _safe_evaluate(self) -> None:
        try:
            await self.evaluate_once()
        except Exception as error:
            self._publish_unknown(error)

    def _publish(self) -> None:
        assert self._snapshot is not None
        report = evaluate(self._snapshot, self.settings)
        self.report(report)
        self.notify_new(report)

    def _publish_unknown(self, error: Exception) -> None:
        now = clock.iso()
        self._snapshot = None
        report = StatusReport(
            state="unknown",
            exit_code=3,
            reasons=[
                Reason(
                    code="status-unreadable",
                    severity="error",
                    service="control",
                    since=now,
                    message=f"Cannot read daemon status: {error}",
                )
            ],
            backlog=Backlog(count=0, seconds=0),
            mode="idle",
            dictation=DictationState(available=False, reason="session-down"),
            ts=now,
        )
        self.report(report)
        self.notify_new(report)

    async def _tick(self) -> None:
        while not self._stop.is_set():
            if await self._wait():
                return
            await self._safe_evaluate()

    async def _wait(self) -> bool:
        try:
            await asyncio.wait_for(
                self._stop.wait(), timeout=self.settings.tray_interval_s
            )
        except TimeoutError:
            return False
        return True

    async def _follow(self) -> None:
        directory = self.roots.run
        directory.mkdir(parents=True, exist_ok=True)
        self.following.set()
        async for _ in watchfiles.awatch(
            directory, debounce=self.debounce_ms, step=5
        ):
            if self._stop.is_set():
                return
            if self._apply_status(directory / "status.json"):
                self._publish()

    def _apply_status(self, path: Path) -> bool:
        if self._snapshot is None:
            return False
        try:
            value: Any = documents.read_json(path)
        except (OSError, ValueError):
            return False
        if not isinstance(value, dict):
            return False
        mode, keys = value.get("mode"), value.get("keys")
        if mode not in MODES or keys not in KEYS:
            return False
        current = self._snapshot.status
        if (current.get("mode"), current.get("keys")) == (mode, keys):
            return False
        self._snapshot.status = {"mode": mode, "keys": keys}
        self._snapshot.now = clock.utc_now()
        return True


def _body(reason: Reason) -> str:
    if reason.fix:
        return f"{reason.message} {reason.fix}"
    return reason.message
