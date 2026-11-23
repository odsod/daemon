def test_append_uses_the_utc_day(tmp_path, monkeypatch):
    """ADR-0003: one stream file per UTC day, also after local midnight."""
    import time
    from datetime import UTC, datetime

    from odsod_daemon.components.interactions import batch
    from odsod_daemon.lib import clock

    monkeypatch.setenv("TZ", "Europe/Stockholm")
    time.tzset()
    monkeypatch.setattr(
        clock, "utc_now", lambda: datetime(2026, 11, 23, 23, 30, tzinfo=UTC)
    )
    try:
        batch.append(tmp_path, {"kind": "test"})  # type: ignore[arg-type]
    finally:
        monkeypatch.undo()
        time.tzset()
    assert [p.name for p in tmp_path.glob("*.jsonl")] == ["2026-11-23.jsonl"]
