"""``odsodctl inference``: set up the servers on the inference host."""

import typer

from odsod_daemon.components.servers import setup

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Set up the inference servers on the inference host.",
)


@app.command("setup")
def setup_command(
    check: bool = typer.Option(False, "--check", help="Print the state only."),
) -> None:
    """Get the pinned models and build the pinned servers."""
    try:
        setup.run(check=check, progress=typer.echo)
    except setup.SetupError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
