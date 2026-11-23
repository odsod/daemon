from pathlib import Path

from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.components.install import source
from odsod_daemon.components.version import cli
from odsod_daemon.lib import documents


def test_vcs(monkeypatch):
    record = source.candidate({"vcs_info": {"commit_id": "a" * 40}})
    monkeypatch.setattr(cli, "candidate", lambda: record)
    result = CliRunner().invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    assert '"commit": "' + "a" * 40 + '"' in result.stdout


def test_dev_uses_deployment_record(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ODSOD_DAEMON_ROOT", str(tmp_path))
    monkeypatch.setattr(source, "_git", lambda *args: "new")
    record = source.candidate({"url": "file:///tmp/work"})
    monkeypatch.setattr(cli, "candidate", lambda: record)
    documents.write_json(
        tmp_path / "state/install/current",
        {
            **record.model_dump(),
            "commit": "old",
            "dirty": True,
        },
    )
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "dev /tmp/work old+dirty"


def test_dev_without_git(monkeypatch):
    def missing(*args):
        raise FileNotFoundError

    monkeypatch.setattr(source, "_git", missing)
    assert source.candidate({"url": "file:///tmp/work"}).commit == "unknown"
