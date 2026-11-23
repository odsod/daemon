"""Tell whether the host runs on mains power.

Device batteries, such as a pen or a mouse, do not count. No supply, or only
device batteries, gives True.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_ROOT = Path("/sys/class/power_supply")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def on_mains(root: Path = DEFAULT_ROOT) -> bool:
    if not root.is_dir():
        return True
    supplies = [entry for entry in root.iterdir() if entry.is_dir()]
    if not supplies:
        return True

    mains_online = False
    system_batteries: list[Path] = []
    for supply in supplies:
        kind = _read(supply / "type")
        if kind == "Mains" and _read(supply / "online") == "1":
            mains_online = True
        if kind == "Battery" and _read(supply / "scope") != "Device":
            system_batteries.append(supply)

    if mains_online or not system_batteries:
        return True
    return not any(
        _read(battery / "status") == "Discharging" for battery in system_batteries
    )
