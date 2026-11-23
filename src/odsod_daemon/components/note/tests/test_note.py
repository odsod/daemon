import json

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.lib import streams


@pytest.mark.parametrize(
    "stdin,as_json", [(False, False), (False, True), (True, False), (True, True)]
)
def test_note(temp_root, stdin, as_json):
    args = ["note", "-" if stdin else "A useful note"] + (["--json"] if as_json else [])
    result = CliRunner().invoke(app, args, input="Piped\nnotes\n" if stdin else None)
    assert result.exit_code == 0, result.output
    files = list((temp_root / "state/events/user").glob("*.jsonl"))
    assert len(files) == 1
    record = streams.read_day(files[0])[0]
    assert record["kind"] == "note"
    assert record["text"] == ("Piped\nnotes\n" if stdin else "A useful note")
    if as_json:
        assert json.loads(result.output) == record
    else:
        assert (
            "**nfo**" in result.output
            and f"<!-- id:note:{record['ts']} -->" in result.output
        )
        assert result.output.count("\n") == 1
