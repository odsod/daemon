from __future__ import annotations

from pathlib import Path

import pytest

from odsod_daemon.lib import power


def supply(
    root: Path,
    name: str,
    *,
    kind: str,
    scope: str | None = None,
    status: str | None = None,
    online: str | None = None,
) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "type").write_text(kind, encoding="utf-8")
    if scope is not None:
        (directory / "scope").write_text(scope, encoding="utf-8")
    if status is not None:
        (directory / "status").write_text(status, encoding="utf-8")
    if online is not None:
        (directory / "online").write_text(online, encoding="utf-8")


@pytest.mark.parametrize("case", ["none", "device", "system", "mains"])
def test_on_mains(tmp_path: Path, case: str) -> None:
    root = tmp_path / "power_supply"
    root.mkdir()
    if case == "device":
        supply(
            root,
            "wacom_battery_1",
            kind="Battery",
            scope="Device",
            status="Discharging",
        )
    if case == "system":
        supply(root, "BAT0", kind="Battery", scope="System", status="Discharging")
    if case == "mains":
        supply(root, "BAT0", kind="Battery", scope="System", status="Discharging")
        supply(root, "AC", kind="Mains", online="1")
    assert power.on_mains(root) is (case != "system")


def test_missing_root_is_mains(tmp_path: Path) -> None:
    assert power.on_mains(tmp_path / "missing") is True


def test_battery_charging_is_mains(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    root.mkdir()
    supply(root, "BAT0", kind="Battery", scope="System", status="Charging")
    assert power.on_mains(root) is True


def test_battery_without_scope_counts_as_system(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    root.mkdir()
    supply(root, "BAT0", kind="Battery", status="Discharging")
    assert power.on_mains(root) is False


def test_mains_without_online_file_is_offline(tmp_path: Path) -> None:
    root = tmp_path / "power_supply"
    root.mkdir()
    supply(root, "BAT0", kind="Battery", scope="System", status="Discharging")
    supply(root, "AC", kind="Mains")
    assert power.on_mains(root) is False
