"""The rsync commands of one sync pass, in order (ADR-0024)."""

from __future__ import annotations

from pathlib import Path

from odsod_daemon.lib import paths

# Dictation ranges and holds go first, so the base never cuts their audio as
# ambient speech before it knows of them.
FIRST = ("events", "utterances/dictation")


def ssh(control: Path) -> str:
    return (
        "ssh -o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=auto"
        f" -o ControlPersist=60 -o ControlPath={control}"
    )


def commands(
    roots: paths.Roots, host: str, base: str, remote_state: str
) -> list[list[str]]:
    target = f"{base}:{remote_state}/{paths.HOSTS}/{paths.check_host(host)}/"
    shell = ssh(roots.run / "sync-ssh")
    # --append sends only bytes past the copy's end: streams and hour files
    # only grow (ADR-0003).
    rsync = ["rsync", "--recursive", "--times", "--append", "--mkpath", "-e", shell]
    result = []
    first = [
        f"{roots.state}/./{name}" for name in FIRST if (roots.state / name).exists()
    ]
    if first:
        result.append([*rsync, "--relative", *first, target])
    status = roots.run / "status.json"
    if status.exists():
        result.append(
            ["rsync", "--times", "--mkpath", "-e", shell, str(status), f"{target}run/"]
        )
    if (roots.state / "audio").exists():
        result.append(
            [
                *rsync,
                "--relative",
                "--sparse",
                "--compress",
                f"{roots.state}/./audio",
                target,
            ]
        )
    return result
