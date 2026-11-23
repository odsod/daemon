import json

from odsod_daemon.components.unmute_stale.cli import cleanup
from odsod_daemon.lib import documents


async def test_unmute_leaves_record(temp_root, monkeypatch):
    from odsod_daemon.components.dictation import pactl

    file = temp_root / "run/muted.json"
    value = {"streams": [{"id": "1", "app": "meeting"}]}
    documents.write_json(file, value)
    calls = []

    async def unmute(streams):
        calls.extend(streams)

    monkeypatch.setattr(pactl, "unmute", unmute)
    # The command imports this function directly.
    monkeypatch.setattr("odsod_daemon.components.unmute_stale.cli.unmute", unmute)
    await cleanup()
    assert calls == [("1", "meeting")]
    assert json.loads(file.read_text()) == value
