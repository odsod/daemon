"""Adapters run one setup over the cases it accepts (ADR-0019)."""

from __future__ import annotations

from typing import Protocol

from odsod_daemon.components.bench import sandbox
from odsod_daemon.components.bench.contract import BenchCase, SetupManifest
from odsod_daemon.components.bench.setups import Setup
from odsod_daemon.lib import paths

SANDBOX_KINDS = {"ambient", "dictation"}


class Adapter(Protocol):
    """A setup runner. A later cloud adapter accepts dictation cases only."""

    def accepts(self, kind: str) -> bool: ...

    def run(
        self, cases: list[BenchCase], *, isolated: bool = False
    ) -> list[sandbox.RunResult]: ...


def check_contract(adapter: Adapter, *, cloud: bool = False) -> None:
    """Refuse an adapter that breaks its rule: a cloud adapter takes dictation."""
    if cloud and adapter.accepts("ambient"):
        raise ValueError("a cloud adapter must accept dictation cases only")


class SandboxAdapter:
    def __init__(
        self,
        setup: Setup,
        manifest: SetupManifest,
        roots: paths.Roots,
    ) -> None:
        self.setup = setup
        self.manifest = manifest
        self.roots = roots

    def accepts(self, kind: str) -> bool:
        return kind in SANDBOX_KINDS

    def run(
        self, cases: list[BenchCase], *, isolated: bool = False
    ) -> list[sandbox.RunResult]:
        return sandbox.run(
            self.setup, self.manifest, self.roots, cases, isolated=isolated
        )
