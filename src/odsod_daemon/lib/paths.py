"""Roots for state, run and config files.

``ODSOD_DAEMON_ROOT`` overrides all three roots. Tests and the bench sandbox
set it to a temp directory.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

OVERRIDE = "ODSOD_DAEMON_ROOT"


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
    """Return the three roots for this process."""
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


def config_file(env: Mapping[str, str] | None = None) -> Path:
    return roots(env).config_file
