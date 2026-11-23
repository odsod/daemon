from __future__ import annotations

from odsod_daemon.components.signals.meeting import End, Meeting, Start
from odsod_daemon.components.signals.platforms.base import MeetingRef

MEET = MeetingRef(
    "meet", "abc-defg-hij", "Standup", "https://meet.google.com/abc-defg-hij"
)
OTHER = MeetingRef(
    "meet", "zzz-yyyy-xxx", "Review", "https://meet.google.com/zzz-yyyy-xxx"
)
RENAMED = MeetingRef(
    "meet",
    "abc-defg-hij",
    "Standup with a longer calendar title",
    "https://meet.google.com/abc-defg-hij",
)


def test_lobby_does_not_start_a_meeting() -> None:
    meeting = Meeting()
    assert meeting.observe(0.0, MEET, 0) == []
    assert meeting.active is None


def test_join_starts_at_once() -> None:
    meeting = Meeting()
    assert meeting.observe(0.0, None, None) == []
    assert meeting.observe(2.0, MEET, 2) == [Start(MEET, 2.0)]
    assert meeting.active == MEET


def test_reload_within_grace_does_not_split() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, MEET, 0) == []
    assert meeting.observe(6.0, MEET, 0) == []
    assert meeting.observe(8.0, MEET, 2) == []
    assert meeting.active == MEET


def test_tiles_gone_past_grace_end_the_meeting() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    meeting.observe(2.0, MEET, 0)
    assert meeting.observe(12.0, MEET, 0) == [End(MEET, 2.0, "left")]
    assert meeting.active is None


def test_tab_closed_ends_at_once() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, None, None) == [End(MEET, 2.0, "tab-closed")]
    assert meeting.active is None


def test_code_change_ends_then_starts() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, OTHER, 2) == [
        End(MEET, 2.0, "tab-closed"),
        Start(OTHER, 2.0),
    ]
    assert meeting.active == OTHER


def test_code_change_to_a_lobby_starts_later() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, OTHER, 0) == [End(MEET, 2.0, "tab-closed")]
    assert meeting.active is None
    assert meeting.observe(4.0, OTHER, 2) == [Start(OTHER, 4.0)]


def test_title_change_keeps_the_meeting_open() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, RENAMED, 2) == []
    assert meeting.active == MEET


def test_unknown_tiles_keep_the_state() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.observe(0.0, MEET, 2)
    assert meeting.observe(2.0, MEET, None) == []
    assert meeting.active == MEET
    assert meeting.observe(20.0, MEET, None) == []
    assert meeting.active == MEET


def test_resume_adopts_an_open_meeting() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.resume(MEET)
    assert meeting.active == MEET
    assert meeting.observe(2.0, MEET, 2) == []


def test_resumed_meeting_ends_when_the_tab_goes() -> None:
    meeting = Meeting(end_grace_s=10)
    meeting.resume(MEET)
    assert meeting.observe(2.0, None, None) == [End(MEET, 2.0, "tab-closed")]
