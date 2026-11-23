"""Expected unit names and commands for their scope."""

from odsod_daemon.components.install.contract import SERVICES

NAMES = ("capture", "pipeline", "session", "tray", "keys")


def unit(service: str) -> str:
    return f"odsod-daemon-{service}.service"


def expected(service: str, *, graphical: bool, paused: bool) -> bool:
    if service not in SERVICES:
        return False
    if service == "capture":
        return graphical and not paused
    if service in ("session", "tray"):
        return graphical
    return True


def fix(service: str) -> str:
    prefix = "sudo systemctl" if service == "keys" else "systemctl --user"
    return f"{prefix} restart odsod-daemon-{service}"
