"""Run one setup over the cases: select, resume, write results."""

from __future__ import annotations

from dataclasses import dataclass

from odsod_daemon.components.bench import cases as bench_cases
from odsod_daemon.components.bench import sandbox, setups
from odsod_daemon.components.bench.adapters import Adapter, SandboxAdapter
from odsod_daemon.components.bench.contract import BenchCase, BenchResult
from odsod_daemon.lib import clock, documents, paths


@dataclass(frozen=True)
class Summary:
    setup: str
    fingerprint: str
    ran: int
    ok: int
    empty: int
    failed: int


def result_path(roots: paths.Roots, case: BenchCase, fingerprint: str):
    return bench_cases.case_dir(roots, case.id) / "results" / f"{fingerprint}.json"


def result(roots: paths.Roots, case: BenchCase, fingerprint: str) -> BenchResult | None:
    path = result_path(roots, case, fingerprint)
    if not path.exists():
        return None
    return BenchResult.model_validate_json(path.read_text())


def select(
    roots: paths.Roots,
    adapter: Adapter,
    *,
    fingerprint: str,
    kind: str | None = None,
    limit: int | None = None,
    retry_failed: bool = False,
) -> list[BenchCase]:
    chosen: list[BenchCase] = []
    for case in sorted(bench_cases.load_cases(roots), key=lambda item: item.start):
        if not adapter.accepts(case.kind):
            continue
        if kind is not None and case.kind != kind:
            continue
        if bench_cases.reference(roots, case) is None:
            continue
        stored = result(roots, case, fingerprint)
        if stored is not None and (stored.outcome != "failed" or not retry_failed):
            continue
        chosen.append(case)
    return chosen if limit is None else chosen[:limit]


def run(
    roots: paths.Roots,
    setup: setups.Setup,
    *,
    kind: str | None = None,
    limit: int | None = None,
    retry_failed: bool = False,
    isolated: bool = False,
) -> Summary:
    """Run the setup over every selected case and write one result each."""
    manifest = setups.manifest(setup, roots)
    adapter = SandboxAdapter(setup, manifest, roots)
    selected = select(
        roots,
        adapter,
        fingerprint=manifest.fingerprint,
        kind=kind,
        limit=limit,
        retry_failed=retry_failed,
    )
    results: list[sandbox.RunResult] = []
    for item in adapter.run(selected, isolated=isolated):
        results.append(item)
        result_value = BenchResult(
            setup=manifest,
            outcome=item.outcome,
            output=item.output,
            latency_ms=item.latency_ms,
            error=item.error,
            ts=clock.iso(),
        )
        documents.write_json(
            result_path(roots, item.case, manifest.fingerprint),
            result_value.model_dump(mode="json", exclude_none=True),
        )
    return Summary(
        setup=setup.name,
        fingerprint=manifest.fingerprint,
        ran=len(results),
        ok=sum(1 for item in results if item.outcome == "ok"),
        empty=sum(1 for item in results if item.outcome == "empty"),
        failed=sum(1 for item in results if item.outcome == "failed"),
    )
