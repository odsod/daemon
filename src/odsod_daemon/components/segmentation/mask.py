"""Dictation masks and the live microphone read limit."""

from odsod_daemon.lib import clock

DICTATION_GUARD = 1.2
DICTATION_STALE = 130


def held_start(status: dict, now: float) -> float | None:
    if status.get("mode") != "dictating":
        return None
    if now - clock.parse_iso(status["since"]).timestamp() > DICTATION_STALE:
        return None
    return clock.parse_iso(status["audio_start"]).timestamp()


def read_limit(newest: float, now: float, status: dict, *, once: bool) -> float:
    if once:
        return newest
    held = held_start(status, now)
    return min(newest, now - DICTATION_GUARD, held if held is not None else newest)


def ranges(records: list[dict]) -> list[tuple[float, float]]:
    return sorted(
        (clock.parse_iso(r["start"]).timestamp(), clock.parse_iso(r["end"]).timestamp())
        for r in records
    )
