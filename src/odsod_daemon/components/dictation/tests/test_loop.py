import pytest

from odsod_daemon.components.dictation import gate
from odsod_daemon.components.dictation.config import MAX_HOLD
from odsod_daemon.components.dictation.loop import Loop
from odsod_daemon.lib import clock


@pytest.mark.parametrize("finish", ["stop", "tick", "cancel", "disconnected"])
async def test_hold(finish):
    loop = Loop()
    assert loop.event("start", 100) == []
    loop.event("connected")
    assert loop.event("start", 100) == ["mute", "dictating"]
    assert loop.start == 99.7
    await clock.sleep(MAX_HOLD if finish == "tick" else 1)
    at = 100 + MAX_HOLD if finish == "tick" else 101
    actions = loop.event(finish, at)
    if finish in {"cancel", "disconnected"}:
        assert actions == ["unmute", "idle"]
        assert loop.event("covered") == []
    else:
        assert actions == ["unmute", "cover"]
        assert loop.end == at + 0.15
        assert loop.event("covered") == ["append", "idle", "queue"]
        assert loop.event("stop", at + 1) == []


def test_capture_stall_and_maximum_hold():
    loop = Loop()
    loop.event("connected")
    loop.event("start", 100)
    assert loop.event("tick", 219) == []
    assert loop.event("tick", 221) == ["unmute", "cover"]
    assert loop.release == 220
    assert loop.event("failed") == ["idle"]


@pytest.mark.parametrize("capture", [False, True])
@pytest.mark.parametrize("reachable", [False, True])
@pytest.mark.parametrize("mains", [False, True])
@pytest.mark.parametrize("loopback", [False, True])
def test_gate(capture, reachable, mains, loopback):
    result = gate.reason(
        capture=capture, reachable=reachable, mains=mains, loopback=loopback
    )
    assert (result == "connected") == (
        capture and reachable and (mains or not loopback)
    )
    assert gate.may_disconnect("idle")
    assert not gate.may_disconnect("dictating")
    assert not gate.may_disconnect("closing")
