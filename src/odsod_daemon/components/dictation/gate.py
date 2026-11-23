"""Pure connection policy. A hold keeps its connection until it ends."""

from odsod_daemon.components.dictation.contract import KeysState


def reason(*, capture: bool, reachable: bool, mains: bool, loopback: bool) -> KeysState:
    if not capture:
        return "paused"
    if not reachable or (not mains and loopback):
        return "no-inference"
    return "connected"


def may_disconnect(state: str) -> bool:
    return state in {"idle", "offline"}
