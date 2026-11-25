"""Roots for state, run and config files.

``ODSOD_DAEMON_ROOT`` overrides all three roots. Tests and the bench sandbox
set it to a temp directory.

On the base, each satellite has a host root under ``state/hosts/<host>/``
(ADR-0024). Inside ``with host(name)`` (and tasks created there),
``roots()`` returns that host root.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

OVERRIDE = "ODSOD_DAEMON_ROOT"
HOSTS = "hosts"
HOST_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")

_host: ContextVar[str | None] = ContextVar("odsod_daemon_host", default=None)


@dataclass(frozen=True)
class Roots:
    state: Path
    run: Path
    config: Path

    def ensure(self) -> Roots:
        """Create the roots with restrictive modes."""
        for path in (self.state, self.run, self.config):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return self

    @property
    def config_file(self) -> Path:
        return self.config / "config.json"


def roots(env: Mapping[str, str] | None = None) -> Roots:
    """Return the roots for this process, or for the current host root."""
    local = local_roots(env)
    name = _host.get()
    if name is None:
        return local
    state = local.state / HOSTS / name
    return Roots(state=state, run=state / "run", config=local.config)


def local_roots(env: Mapping[str, str] | None = None) -> Roots:
    """Return this host's own roots, whatever the current host root is."""
    env = os.environ if env is None else env
    override = env.get(OVERRIDE)
    if override:
        base = Path(override)
        return Roots(state=base / "state", run=base / "run", config=base / "config")

    home = Path(env.get("HOME", str(Path.home())))
    state_home = Path(env.get("XDG_STATE_HOME", home / ".local/state"))
    config_home = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
    runtime = env.get("XDG_RUNTIME_DIR")
    run_root = Path(runtime) if runtime else Path("/run/user") / str(os.getuid())
    return Roots(
        state=state_home / "odsod-daemon",
        run=run_root / "odsod-daemon",
        config=config_home / "odsod-daemon",
    )


def current_host() -> str | None:
    """The satellite whose host root is current, or None for this host."""
    return _host.get()


def check_host(name: str) -> str:
    if not HOST_NAME.fullmatch(name):
        raise ValueError(f"bad host name: {name!r}")
    return name


@contextmanager
def host(name: str) -> Iterator[None]:
    """Make ``roots()`` return the host root of ``name``."""
    token = _host.set(check_host(name))
    try:
        yield
    finally:
        _host.reset(token)


def satellites(
    env: Mapping[str, str] | None = None, *, state: Path | None = None
) -> list[str]:
    """Host names that have a host root on this host (or under ``state``)."""
    directory = (state or local_roots(env).state) / HOSTS
    if not directory.is_dir():
        return []
    return sorted(
        p.name
        for p in directory.iterdir()
        if p.is_dir() and HOST_NAME.fullmatch(p.name)
    )


def config_file(env: Mapping[str, str] | None = None) -> Path:
    return roots(env).config_file
