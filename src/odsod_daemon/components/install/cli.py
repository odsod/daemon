"""Install the user units, or the separately owned system service."""

import sys
from pathlib import Path

import typer

from odsod_daemon.components.install.apply import ApplyError, install_user
from odsod_daemon.components.install.system import SystemError, install_system

app = typer.Typer(add_completion=False)


@app.callback(invoke_without_command=True)
def install_command(system: bool = typer.Option(False, "--system")) -> None:
    """Apply the installed package to this host."""
    try:
        if system:
            install_system()
        else:
            install_user(command=Path(sys.argv[0]).resolve(), progress=typer.echo)
    except (ApplyError, SystemError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
