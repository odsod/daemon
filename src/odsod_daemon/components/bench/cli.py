"""``odsodctl bench``: build, run and score cases (ADR-0019)."""

from __future__ import annotations

import importlib.util
from typing import Annotated

import typer
from pydantic import BaseModel, Field, ValidationError

from odsod_daemon.components.bench import cases, setups
from odsod_daemon.components.bench.contract import BenchCase, Review
from odsod_daemon.lib import cli, clock, config, paths

app = typer.Typer(add_completion=False, help="Build, run and score bench cases.")

INSTALL = "uv tool install 'odsod-daemon[bench]'"


class CaseLine(BaseModel):
    id: str
    kind: str
    channel: str | None = None
    language: str | None = None
    length_s: float
    state: str
    start: str
    end: str


class CaseList(BaseModel):
    cases: list[CaseLine] = Field(default_factory=list)


class CasesResult(BaseModel):
    written: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
    deleted: list[str] = Field(default_factory=list)


class AcceptResult(BaseModel):
    cases: dict[str, Review] = Field(default_factory=dict)


class RunResult(BaseModel):
    setup: str
    fingerprint: str
    ran: int
    ok: int
    empty: int
    failed: int


def _bench() -> setups.Bench:
    try:
        return config.section("bench", setups.Bench)
    except (config.ConfigError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


def _require_extra() -> None:
    if importlib.util.find_spec("jiwer") is None:
        typer.echo(f"bench needs its extra: {INSTALL}", err=True)
        raise typer.Exit(1)


def _review_state(roots: paths.Roots, case: BenchCase) -> str:
    stored = cases.review(roots, case)
    if stored.state == "accepted" and not cases.is_accepted(roots, case):
        return "draft"
    return stored.state


def _line(roots: paths.Roots, case: BenchCase) -> CaseLine:
    start, end = clock.parse_iso(case.start), clock.parse_iso(case.end)
    return CaseLine(
        id=case.id,
        kind=case.kind,
        channel=case.channel,
        language=case.language,
        length_s=round((end - start).total_seconds(), 3),
        state=_review_state(roots, case),
        start=case.start,
        end=case.end,
    )


@app.callback()
def _check_extra() -> None:
    _require_extra()


@app.command("cases")
def cases_command(
    ambient: int | None = typer.Option(None, "--ambient", help="Cases per stratum."),
    dictation: int | None = typer.Option(None, "--dictation"),
    interactions: int | None = typer.Option(None, "--interactions"),
    as_json: bool = typer.Option(False, "--json", help="Print one JSON document."),
) -> None:
    """Build new cases from the stored audio and text."""
    section = _bench()
    roots = paths.roots()
    targets = section.cases
    for name, value in (
        ("--ambient", ambient),
        ("--dictation", dictation),
        ("--interactions", interactions),
    ):
        if value is not None and value < 0:
            raise typer.BadParameter("must not be negative", param_hint=name)
    written = cases.top_up(
        roots,
        targets,
        seed=targets.seed,
        ambient=ambient,
        dictation=dictation,
        interactions=interactions,
    )
    result = CasesResult(written=written)
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: (
            f"wrote {len(value.written)} cases"
            + (": " + ", ".join(value.written) if value.written else "")
        ),
    )


@app.command("list")
def list_command(
    kind: str | None = typer.Option(None, "--kind"),
    state: str | None = typer.Option(None, "--state"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List one line per case."""
    roots = paths.roots()
    lines = [
        _line(roots, case)
        for case in cases.load_cases(roots)
        if (kind is None or case.kind == kind)
    ]
    if state is not None:
        lines = [line for line in lines if line.state == state]
    result = CaseList(cases=lines)
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: "\n".join(
            f"{line.id} {line.kind} {line.channel or '-'} {line.language or '-'} "
            f"{line.length_s:.1f}s {line.state}"
            for line in value.cases
        ),
    )


@app.command("delete")
def delete_command(
    case_ids: Annotated[list[str], typer.Argument()],
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Remove case directories and their results."""
    try:
        deleted = cases.delete(paths.roots(), case_ids)
    except KeyError as error:
        typer.echo(error.args[0], err=True)
        raise typer.Exit(1) from error
    result = DeleteResult(deleted=deleted)
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: f"deleted {len(value.deleted)} cases",
    )


@app.command("accept")
def accept_command(
    case_ids: Annotated[list[str], typer.Argument()],
    by: str = typer.Option("owner", "--by"),
    draft_by: str | None = typer.Option(None, "--draft-by"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Accept references, or record who drafted them."""
    try:
        written = cases.accept(paths.roots(), case_ids, by=by, draft_by=draft_by)
    except KeyError as error:
        typer.echo(error.args[0], err=True)
        raise typer.Exit(1) from error
    result = AcceptResult(
        cases={
            case_id: review for case_id, review in zip(case_ids, written, strict=True)
        }
    )
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: "\n".join(
            f"{case_id}: {review.state}" for case_id, review in value.cases.items()
        ),
    )


@app.command("run")
def run_command(
    name: str = typer.Argument(...),
    kind: str | None = typer.Option(None, "--kind"),
    limit: int | None = typer.Option(None, "--limit"),
    retry_failed: bool = typer.Option(False, "--retry-failed"),
    isolated: bool = typer.Option(False, "--isolated"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run one setup over the cases with a reference."""
    from odsod_daemon.components.bench import runner

    section = _bench()
    try:
        setup = section.setup(name)
    except KeyError as error:
        typer.echo(error.args[0], err=True)
        raise typer.Exit(1) from error
    try:
        summary = runner.run(
            paths.roots(),
            setup,
            kind=kind,
            limit=limit,
            retry_failed=retry_failed,
            isolated=isolated,
        )
    except (ValueError, RuntimeError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    result = RunResult(
        setup=summary.setup,
        fingerprint=summary.fingerprint,
        ran=summary.ran,
        ok=summary.ok,
        empty=summary.empty,
        failed=summary.failed,
    )
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: (
            f"{value.setup}: ran {value.ran} cases "
            f"({value.ok} ok, {value.empty} empty, {value.failed} failed)"
        ),
    )


@app.command("report")
def report_command(
    setup: str | None = typer.Option(None, "--setup"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Score the saved results per measure, group and setup."""
    from odsod_daemon.components.bench import report

    result = report.report(paths.roots(), setup=setup)
    cli.emit(
        result,
        as_json=as_json,
        text=lambda value: report.render(value.rows),
    )


__all__ = ["app"]
