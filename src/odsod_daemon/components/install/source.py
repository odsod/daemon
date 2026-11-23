"""Read PEP 610 metadata and the source of a local deployment."""

from __future__ import annotations

import json
import subprocess
from importlib.metadata import distribution
from pathlib import Path
from urllib.parse import unquote, urlparse

from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.lib import clock


def candidate(metadata: dict | None = None) -> InstallRecord:
    if metadata is None:
        raw = distribution("odsod-daemon").read_text("direct_url.json")
        if raw is None:
            raise ValueError("odsod-daemon has no direct_url.json")
        metadata = json.loads(raw)
    assert metadata is not None
    vcs = metadata.get("vcs_info")
    if vcs:
        return InstallRecord(
            source="git", commit=vcs["commit_id"], installed_at=clock.iso()
        )
    url = urlparse(metadata["url"])
    if url.scheme != "file":
        raise ValueError("install source must be a Git or local directory install")
    workspace = Path(unquote(url.path)).resolve()
    commit, dirty = "unknown", False
    try:
        commit = _git(workspace, "rev-parse", "HEAD")
        dirty = bool(_git(workspace, "status", "--porcelain"))
    except OSError, subprocess.SubprocessError:
        pass
    return InstallRecord(
        source="dev",
        commit=commit,
        workspace=str(workspace),
        dirty=dirty,
        installed_at=clock.iso(),
    )


def _git(workspace: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(workspace), *args],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=10,
    ).strip()
