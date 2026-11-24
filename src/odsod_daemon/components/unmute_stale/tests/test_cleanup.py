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


async def test_cleanup_mutes_the_recorded_mic_again(temp_root, monkeypatch):
    """PRD dictation AC-26: a stop or crash during a hold mutes the mic again."""
    from odsod_daemon.components.dictation import pactl

    documents.write_json(temp_root / "run/muted.json", {"streams": [], "source": "mic"})
    calls = []

    async def unmute(streams):
        calls.append(("unmute", streams))

    async def set_source_mute(name, muted):
        calls.append(("source", name, muted))

    monkeypatch.setattr("odsod_daemon.components.unmute_stale.cli.unmute", unmute)
    monkeypatch.setattr(pactl, "set_source_mute", set_source_mute)
    await cleanup()
    assert ("source", "mic", True) in calls
