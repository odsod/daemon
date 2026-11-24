"""Architecture checks for the seams of ADR-0009 and ADR-0010."""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

from odsod_daemon import components

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "odsod_daemon"
PACKAGE = "odsod_daemon"
COMPONENTS = "odsod_daemon.components"

SUBSYSTEMS = {
    "keys": "keys",
    "capture": "capture",
    "retention": "capture",
    "audio": "capture",
    "segmentation": "speech",
    "transcription": "speech",
    "cleanup": "speech",
    "parakeet": "speech",
    "dictation": "dictation",
    "unmute_stale": "dictation",
    "signals": "signals",
    "transcript": "transcript",
    "note": "transcript",
    "pin": "transcript",
    "interactions": "interactions",
    "publish": "publishing",
    "health": "control",
    "status": "control",
    "pause": "control",
    "resume": "control",
    "tray": "control",
    "notify_failed": "control",
    "bench": "bench",
    "shortcuts": "shortcuts",
    "install": "install",
    "version": "install",
    "servers": "inference",
}


def _modules() -> list[str]:
    return [
        info.name for info in pkgutil.iter_modules(components.__path__) if info.ispkg
    ]


def test_component_folders_match_the_table() -> None:
    assert set(_modules()) == set(SUBSYSTEMS)


def test_every_component_sets_its_subsystem() -> None:
    for name, subsystem in SUBSYSTEMS.items():
        module = importlib.import_module(f"{COMPONENTS}.{name}")
        assert subsystem == module.SUBSYSTEM, name
        assert (SRC / "components" / name / "contract.py").is_file(), name


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _component_of(path: Path) -> str | None:
    parts = path.relative_to(SRC).parts
    if len(parts) >= 3 and parts[0] == "components":
        return parts[1]
    return None


def _absolute_imports(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
            if node.module == COMPONENTS:
                modules.extend(f"{COMPONENTS}.{alias.name}" for alias in node.names)
    return modules


def _cross_subsystem_offenders(source: str, current: str) -> list[str]:
    """Imports in ``source`` that reach another subsystem outside its contract."""
    offenders: list[str] = []
    for module in _absolute_imports(ast.parse(source)):
        if not module.startswith(f"{COMPONENTS}."):
            continue
        parts = module.split(".")
        if len(parts) < 3:
            continue
        target = parts[2]
        if target == current:
            continue
        if SUBSYSTEMS.get(target) == SUBSYSTEMS[current]:
            continue
        expected = f"{COMPONENTS}.{target}.contract"
        if module != expected:
            offenders.append(module)
    return offenders


def test_relative_imports_are_not_used() -> None:
    offenders: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_cross_subsystem_imports_go_through_contract() -> None:
    offenders: list[str] = []
    for path in _source_files():
        current = _component_of(path)
        if current is None:
            continue
        source = path.read_text(encoding="utf-8")
        for module in _cross_subsystem_offenders(source, current):
            offenders.append(f"{path.relative_to(ROOT)}: {module}")
    assert offenders == []


def test_component_of_sees_top_level_files() -> None:
    top_level = SRC / "components" / "capture" / "segment.py"
    nested = SRC / "components" / "capture" / "tests" / "test_segment.py"
    assert _component_of(top_level) == "capture"
    assert _component_of(nested) == "capture"
    assert _component_of(SRC / "lib" / "audio.py") is None


def test_cross_subsystem_check_sees_package_imports() -> None:
    source = "from odsod_daemon.components import signals\n"
    assert _cross_subsystem_offenders(source, "capture") == [
        "odsod_daemon.components.signals"
    ]
    contract = "from odsod_daemon.components.signals.contract import Event\n"
    assert _cross_subsystem_offenders(contract, "capture") == []
    same = "from odsod_daemon.components.segmentation import cut\n"
    assert _cross_subsystem_offenders(same, "transcription") == []


def test_lib_imports_no_component() -> None:
    offenders: list[str] = []
    for path in (SRC / "lib").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _absolute_imports(tree):
            if module.startswith(f"{COMPONENTS}."):
                offenders.append(f"{path.relative_to(ROOT)}: {module}")
    assert offenders == []


def _forbidden_time_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "time" and func.attr in {"time", "monotonic"}:
            return True
        if func.value.id == "datetime" and func.attr in {"now", "utcnow"}:
            return True
    return bool(
        isinstance(func, ast.Attribute)
        and func.attr in {"now", "utcnow"}
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "datetime"
    )


def test_only_clock_reads_the_clock() -> None:
    offenders: list[str] = []
    allowed = SRC / "lib" / "clock.py"
    for path in _source_files():
        if path == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _forbidden_time_call(node):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_package_root_holds_only_the_four_tiers() -> None:
    entries = {
        entry.name
        for entry in SRC.iterdir()
        if entry.name != "__pycache__" and not entry.name.endswith(".pyc")
    }
    assert entries == {"__init__.py", "cli.py", "components", "lib", "services"}


@pytest.mark.parametrize("tier", ["cli.py", "services", "components", "lib"])
def test_tiers_exist(tier: str) -> None:
    assert (SRC / tier).exists()
