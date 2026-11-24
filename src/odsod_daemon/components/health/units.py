"""Expected unit names and commands for their scope."""

from odsod_daemon.components.install.contract import SERVICES
from odsod_daemon.components.servers.contract import SERVERS as SERVER_UNITS

SERVERS = tuple(server.name for server in SERVER_UNITS)
NAMES = ("capture", "pipeline", "session", "tray", "keys", *SERVERS)


def unit(service: str) -> str:
    return f"odsod-daemon-{service}.service"


def shipped(service: str, *, inference: bool) -> bool:
    """Installed on this host: a server only where inference is enabled."""
    return inference if service in SERVERS else service in SERVICES


def expected(
    service: str, *, graphical: bool, paused: bool, inference: bool = False
) -> bool:
    if not shipped(service, inference=inference):
        return False
    if service == "capture":
        return graphical and not paused
    if service in ("session", "tray"):
        return graphical
    return True


def fix(service: str) -> str:
    prefix = "sudo systemctl" if service == "keys" else "systemctl --user"
    return f"{prefix} restart odsod-daemon-{service}"
