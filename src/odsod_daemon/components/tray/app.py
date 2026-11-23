"""Run Qt on the main thread with the tray icon and menu."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from odsod_daemon.components.health.config import ControlConfig
from odsod_daemon.components.health.contract import StatusReport
from odsod_daemon.components.tray import menu, worker
from odsod_daemon.lib import paths, systemd


class Bridge(QObject):
    report = Signal(object)


def odsodctl() -> str:
    """The odsodctl next to this interpreter; the unit PATH may lack it."""
    command = Path(sys.executable).with_name("odsodctl")
    return str(command) if command.is_file() else "odsodctl"


def _start(args: list[str]) -> bool:
    started, _pid = QProcess.startDetached(odsodctl(), args)
    return started


class TrayApp(QObject):
    def __init__(self, *, start: Callable[[list[str]], bool] = _start) -> None:
        super().__init__()
        self._start = start
        self.state = ""
        self.tooltip = ""
        self.model: menu.Model | None = None
        self.icon = QSystemTrayIcon()
        self.menu = QMenu()
        self.icon.setContextMenu(self.menu)

    def show(self) -> None:
        self.icon.show()

    @Slot(object)
    def apply(self, report: StatusReport) -> None:
        self.state = report.state
        self.tooltip = menu.tooltip(report)
        self.icon.setToolTip(self.tooltip)
        self.icon.setIcon(QIcon(str(menu.icon_path(report))))
        model = menu.build(report)
        if model == self.model:
            return
        self.model = model
        self.menu.clear()
        for line in model.lines:
            action = self.menu.addAction(line.text)
            action.setEnabled(False)
        if model.lines:
            self.menu.addSeparator()
        action = self.menu.addAction(model.action.capitalize())
        action.triggered.connect(lambda _checked=False: self._run(model.action))

    def _run(self, action: str) -> None:
        self._start([action, "--by", "tray"])


def run(
    roots: paths.Roots, source: systemd.UnitStateSource, settings: ControlConfig
) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    bridge = Bridge()
    tray = TrayApp()
    bridge.report.connect(tray.apply, Qt.ConnectionType.QueuedConnection)
    background = worker.TrayWorker(roots, source, settings, report=bridge.report.emit)
    thread = threading.Thread(
        target=lambda: asyncio.run(background.run()),
        name="tray-worker",
        daemon=True,
    )
    thread.start()
    tray.show()
    try:
        return application.exec()
    finally:
        background.stop()
        thread.join(timeout=2)
