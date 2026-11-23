import json

import pytest
from typer.testing import CliRunner

from odsod_daemon.cli import app
from odsod_daemon.lib import streams


@pytest.mark.parametrize(
    "text,as_json", [("", False), ("", True), ("New topic", False), ("New topic", True)]
)
def test_pin(temp_root, text, as_json):
    result = CliRunner().invoke(
        app, ["pin"] + ([text] if text else []) + (["--json"] if as_json else [])
    )
    assert result.exit_code == 0, result.output
    file = next((temp_root / "state/events/user").glob("*.jsonl"))
    record = streams.read_day(file)[0]
    assert record["kind"] == "pin" and record["text"] == text
    if as_json:
        assert json.loads(result.output) == record
    else:
        assert "**pin**" in result.output
