"""``odsodctl shortcuts``: print the shortcut list. Reads no D-Bus."""

import shlex

import typer

from odsod_daemon.components.shortcuts import contract
from odsod_daemon.components.shortcuts.contract import ShortcutList
from odsod_daemon.lib import cli

app = typer.Typer(add_completion=False)


def render(value: ShortcutList) -> str:
    width = max((len(s.key) for s in value.shortcuts), default=0)
    lines = []
    for shortcut in value.shortcuts:
        command = shlex.join(shortcut.command)
        line = f"{shortcut.key:<{width}}  {shortcut.kind:<7}  {shortcut.name}"
        lines.append(f"{line}  {command}".rstrip())
    return "\n".join(lines)


@app.callback(invoke_without_command=True)
def shortcuts_command(as_json: bool = typer.Option(False, "--json")) -> None:
    """Print every chord with its kind, action and command."""
    cli.emit(contract.load(), as_json=as_json, text=render)
