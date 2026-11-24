"""Get the pinned models and build the pinned servers. Idempotent, no root."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tarfile
from collections.abc import Callable, Mapping
from pathlib import Path

from odsod_daemon.components.servers import pins
from odsod_daemon.components.servers.steps import (
    Found,
    describe,
    missing_tools,
    steps,
)
from odsod_daemon.lib import download, paths
from odsod_daemon.lib.download import Pin


class SetupError(RuntimeError):
    """A setup step failed. Nothing half done is left in place."""


def legacy_root(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    home = Path(env.get("HOME", str(Path.home())))
    data = Path(env.get("XDG_DATA_HOME", str(home / ".local/share")))
    return data / pins.LEGACY


def legacy_file(legacy: Path, server: str, model: Pin) -> Path:
    return legacy / server / model.name


def inspect(state: Path, legacy: Path, build: pins.Build, model: Pin) -> Found:
    source = state / "servers" / build.directory
    old = legacy_file(legacy, build.server, model)
    return Found(
        model=download.present(state / "models", model),
        legacy=old.is_file() and old.stat().st_size == model.size,
        source=(source / "CMakeLists.txt").is_file(),
        binary=os.access(state / build.binary, os.X_OK),
    )


def fetch(directory: Path, pin: Pin, progress: Callable[[str], None]) -> None:
    progress(f"downloading {pin.name} ({pin.size / 1e9:.2f} GB)")
    try:
        asyncio.run(download.fetch(directory, [pin]))
    except download.DownloadError as error:
        raise SetupError(str(error)) from error


def adopt(old: Path, models: Path, pin: Pin, progress: Callable[[str], None]) -> bool:
    """Move a matching model from the machine data dir. False on a mismatch."""
    progress(f"checking {old}")
    if download.sha256(old) != pin.sha256:
        progress(f"{old}: SHA-256 does not match the pin; downloading instead")
        return False
    models.mkdir(parents=True, exist_ok=True)
    partial = models / f"{pin.name}.part"
    shutil.move(old, partial)
    partial.replace(models / pin.name)
    return True


def unpack(tarball: Path, directory: Path, top: str) -> None:
    staging = directory / f".{top}.unpack"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with tarfile.open(tarball) as archive:
            archive.extractall(staging, filter="data")
    except (tarfile.TarError, OSError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise SetupError(f"{tarball.name}: {error}") from error
    if not (staging / top / "CMakeLists.txt").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise SetupError(f"{tarball.name}: no {top}/CMakeLists.txt")
    target = directory / top
    shutil.rmtree(target, ignore_errors=True)
    (staging / top).rename(target)
    shutil.rmtree(staging)
    tarball.unlink()


def build(state: Path, spec: pins.Build, progress: Callable[[str], None]) -> None:
    source = state / "servers" / spec.directory
    jobs = f"-j{os.cpu_count() or 1}"
    progress(f"building {spec.target} {spec.version}")
    for command in (
        ["cmake", "-B", "build", *spec.cmake],
        ["cmake", "--build", "build", "--target", spec.target, jobs],
    ):
        try:
            subprocess.run(command, cwd=source, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise SetupError(f"{spec.target}: {' '.join(command)}: {error}") from error
    if not os.access(state / spec.binary, os.X_OK):
        raise SetupError(f"{spec.target}: the build made no {spec.binary}")


def run(
    *,
    check: bool = False,
    builds: Mapping[str, pins.Build] = pins.BUILDS,
    models: Mapping[str, Pin] = pins.MODELS,
    legacy: Path | None = None,
    progress: Callable[[str], None] = print,
) -> list[str]:
    """Make each server ready. Return what changed; ``check`` changes nothing."""
    state = paths.roots().state
    legacy = legacy_root() if legacy is None else legacy
    found = {
        name: inspect(state, legacy, builds[name], models[name]) for name in builds
    }
    for name, item in found.items():
        progress(describe(name, item))
    if check:
        return []
    todo = {name: steps(item) for name, item in found.items()}
    if any("build" in item for item in todo.values()):
        missing = missing_tools(
            pins.TOOLS, {tool for tool in pins.TOOLS if shutil.which(tool)}
        )
        if missing:
            raise SetupError(
                f"missing build tools: {', '.join(missing)}. "
                f"Install the packages {' '.join(pins.PACKAGES)}. "
                "The machine repo installs them on the inference host."
            )
    changes: list[str] = []
    for name, item in todo.items():
        spec, model = builds[name], models[name]
        for step in item:
            if step == "adopt":
                old = legacy_file(legacy, name, model)
                if adopt(old, state / "models", model, progress):
                    changes.append(f"{name}: adopted {model.name} from {old.parent}")
                    continue
                step = "download-model"
            if step == "download-model":
                fetch(state / "models", model, progress)
                changes.append(f"{name}: downloaded {model.name}")
            elif step == "download-source":
                directory = state / "servers"
                fetch(directory, spec.source, progress)
                unpack(directory / spec.source.name, directory, spec.directory)
                changes.append(f"{name}: downloaded {spec.directory}")
            elif step == "build":
                build(state, spec, progress)
                changes.append(f"{name}: built {spec.target} {spec.version}")
    for line in changes or ["nothing to do: both servers are ready"]:
        progress(line)
    return changes
