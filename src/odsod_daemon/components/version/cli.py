"""Show the deployed source, without querying a moved dev workspace."""

import typer

from odsod_daemon.components.install import source as install_source
from odsod_daemon.components.install.contract import InstallRecord
from odsod_daemon.components.version.contract import VersionReport
from odsod_daemon.lib import cli, documents, paths

app = typer.Typer(add_completion=False)


def report() -> VersionReport:
    metadata = install_source.direct_url()
    source = None
    if not metadata.get("vcs_info"):
        path = paths.roots().state / "install/current"
        if path.exists():
            source = InstallRecord.model_validate(documents.read_json(path))
    source = source or install_source.candidate(metadata)
    return VersionReport.model_validate(source.model_dump())


def render(value: VersionReport) -> str:
    if value.source == "git":
        return value.commit
    suffix = "+dirty" if value.dirty else ""
    return f"dev {value.workspace} {value.commit}{suffix}"


@app.callback(invoke_without_command=True)
def version_command(as_json: bool = typer.Option(False, "--json")) -> None:
    """Print the installed commit or dev deployment."""
    try:
        cli.emit(report(), as_json=as_json, text=render)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
