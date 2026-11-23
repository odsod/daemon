"""The ``odsodctl`` entry point.

The root mounts ``run`` and ``config check``. Each component plan enables its
own line in the list of component commands.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType

import typer
from pydantic import BaseModel

from odsod_daemon.components.note.cli import app as note_app
from odsod_daemon.components.pin.cli import app as pin_app
from odsod_daemon.components.retention.cli import app as retention_app
from odsod_daemon.components.transcript.cli import app as transcript_app
from odsod_daemon.lib import cli as output
from odsod_daemon.lib import config
from odsod_daemon.services import SERVICES
from odsod_daemon.services.runner import (
    ComponentNotBuilt,
    load_component,
    run_component,
    run_service,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="The odsod daemon control CLI.",
)
config_app = typer.Typer(
    no_args_is_help=True,
    help="Inspect and validate the config.",
)
app.add_typer(config_app, name="config")
app.add_typer(note_app, name="note")
app.add_typer(pin_app, name="pin")
app.add_typer(transcript_app, name="transcript")

# Each component plan enables its own line below.
# from odsod_daemon.components.status.cli import app as status_app
# app.add_typer(status_app, name="status")
# from odsod_daemon.components.pause.cli import app as pause_app
# app.add_typer(pause_app, name="pause")
# from odsod_daemon.components.resume.cli import app as resume_app
# app.add_typer(resume_app, name="resume")
# from odsod_daemon.components.notify_failed.cli import app as notify_failed_app
# app.add_typer(notify_failed_app, name="notify-failed")
# from odsod_daemon.components.dictation.cli import app as dictation_app
# app.add_typer(dictation_app, name="dictation")
# from odsod_daemon.components.unmute_stale.cli import app as unmute_stale_app
# app.add_typer(unmute_stale_app, name="unmute-stale")
app.add_typer(retention_app, name="retention")
# from odsod_daemon.components.shortcuts.cli import app as shortcuts_app
# app.add_typer(shortcuts_app, name="shortcuts")
# from odsod_daemon.components.bench.cli import app as bench_app
# app.add_typer(bench_app, name="bench")
# from odsod_daemon.components.install.cli import app as install_app
# app.add_typer(install_app, name="install")
# from odsod_daemon.components.version.cli import app as version_app
# app.add_typer(version_app, name="version")


class CheckResult(BaseModel):
    ok: bool
    errors: list[str] = []


def _component_modules() -> Iterator[ModuleType]:
    package = importlib.import_module("odsod_daemon.components")
    for info in pkgutil.iter_modules(package.__path__):
        if info.ispkg:
            yield importlib.import_module(f"odsod_daemon.components.{info.name}")


def _section_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}
    for module in _component_modules():
        model = getattr(module, "CONFIG_MODEL", None)
        if isinstance(model, type) and issubclass(model, BaseModel):
            models[module.SUBSYSTEM] = model
    return models


def _check_text(result: CheckResult) -> str:
    if result.ok:
        return "config ok"
    return "\n".join(result.errors)


@app.command("run")
def run_command(
    target: str = typer.Argument(..., help="Service or component name."),
    once: bool = typer.Option(False, "--once", help="Drain pending work and exit."),
) -> None:
    """Run one service or one component."""
    try:
        spec = SERVICES.get(target)
        if spec is not None:
            asyncio.run(run_service(spec, once=once))
        else:
            asyncio.run(run_component(load_component(target), once=once))
    except ComponentNotBuilt as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    except ModuleNotFoundError as error:
        typer.echo(f"{target}: no such service or component", err=True)
        raise typer.Exit(2) from error
    except ValueError as error:
        typer.echo(f"{target}: {error}", err=True)
        raise typer.Exit(2) from error


@config_app.command("check")
def config_check(
    as_json: bool = typer.Option(False, "--json", help="Print one JSON document."),
) -> None:
    """Load every config section and report all errors."""
    errors = config.check(_section_models())
    result = CheckResult(ok=not errors, errors=errors)
    output.emit(result, as_json=as_json, text=_check_text)
    if not result.ok:
        raise typer.Exit(1)
