"""Read the newest hold and its text, including late results."""

from datetime import timedelta

from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.lib import clock, paths, streams


def newest(timeout_s: float = DictationConfig().text_timeout_s) -> dict:
    root = paths.roots().state
    today = clock.utc_now().date()
    holds = streams.read_days(
        root / "utterances/dictation", today - timedelta(days=1), today
    )
    if not holds:
        return {"state": "none", "text": ""}
    hold = holds[-1]
    records = streams.read_days(root / "text", today - timedelta(days=1), today)
    text = next((r for r in reversed(records) if r["input"] == hold["id"]), None)
    if text is None:
        return {**hold, "state": "pending", "text": ""}
    late = (
        clock.parse_iso(text["ts"]) - clock.parse_iso(hold["release"])
    ).total_seconds() > timeout_s
    return {
        **hold,
        "state": text["outcome"],
        "text": text["text"],
        "raw": text.get("raw", False),
        "late": late,
    }
