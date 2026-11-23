"""One bounded notify-send call, without Qt or service state."""

import subprocess

from odsod_daemon.components.notify_failed.contract import Notification


def send(notification: Notification) -> bool:
    try:
        result = subprocess.run(
            [
                "notify-send",
                f"--urgency={notification.urgency}",
                "--app-name=odsod-daemon",
                "--",
                notification.title,
                notification.body,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except OSError, subprocess.SubprocessError:
        return False
