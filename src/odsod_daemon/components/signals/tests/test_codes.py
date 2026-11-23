from __future__ import annotations

import pytest

from odsod_daemon.components.signals.platforms.base import slug
from odsod_daemon.components.signals.platforms.meet import Meet
from odsod_daemon.components.signals.platforms.teams import Teams

MEET = Meet()
TEAMS = Teams()


@pytest.mark.parametrize(
    ("url", "code", "clean"),
    [
        (
            "https://meet.google.com/abc-defg-hij",
            "abc-defg-hij",
            "https://meet.google.com/abc-defg-hij",
        ),
        (
            "https://meet.google.com/abc-defg-hij/",
            "abc-defg-hij",
            "https://meet.google.com/abc-defg-hij/",
        ),
        (
            "https://meet.google.com/abc-defg-hij?authuser=0",
            "abc-defg-hij",
            "https://meet.google.com/abc-defg-hij",
        ),
    ],
)
def test_meet_urls_and_codes(url: str, code: str, clean: str) -> None:
    ref = MEET.meeting(url, "Meet \u2013 Standup")
    assert ref is not None
    assert ref.platform == "meet"
    assert ref.code == code
    assert ref.url == clean


@pytest.mark.parametrize(
    "url",
    [
        "https://meet.google.com/",
        "https://meet.google.com/lookup/abc",
        "https://meet.google.com/abc-defg-hij/extra",
        "https://meet.google.com/ABC-DEFG-HIJ",
        "https://meet.google.com.evil.example/abc-defg-hij",
        "https://teams.microsoft.com/l/meetup-join/abc",
        "",
    ],
)
def test_not_a_meet_tab(url: str) -> None:
    assert MEET.meeting(url, "whatever") is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Meet \u2013 Standup", "Standup"),
        ("Meet - Standup", "Standup"),
        ("Meet \u2014 Standup", "Standup"),
        ("Google Meet - Standup", "Standup"),
        ("Standup", "Standup"),
        ("", "abc-defg-hij"),
    ],
)
def test_meet_titles(title: str, expected: str) -> None:
    ref = MEET.meeting("https://meet.google.com/abc-defg-hij", title)
    assert ref is not None
    assert ref.title == expected


def test_teams_thread_id_from_the_url() -> None:
    url = (
        "https://teams.microsoft.com/l/meetup-join/"
        "19%3ameeting_NDQ4ZT%40thread.v2/0?context=%7b%7d"
    )
    ref = TEAMS.meeting(url, "Weekly sync | Microsoft Teams")
    assert ref is not None
    assert ref.code == "19:meeting_NDQ4ZT@thread.v2"
    assert ref.title == "Weekly sync"
    assert ref.url == (
        "https://teams.microsoft.com/l/meetup-join/19%3ameeting_NDQ4ZT%40thread.v2/0"
    )


def test_teams_plain_thread_id() -> None:
    url = "https://teams.live.com/l/meetup-join/19:meeting_abc@thread.v2/0"
    ref = TEAMS.meeting(url, "")
    assert ref is not None
    assert ref.code == "19:meeting_abc@thread.v2"
    assert ref.title == "19:meeting_abc@thread.v2"


def test_teams_title_slug_without_a_thread_id() -> None:
    ref = TEAMS.meeting(
        "https://teams.microsoft.com/l/chat/0/0?users=alice",
        "Weekly sync | Microsoft Teams",
    )
    assert ref is not None
    assert ref.code == "title:weekly-sync"
    assert ref.title == "Weekly sync"


def test_teams_title_slug_is_ascii_and_bounded() -> None:
    ref = TEAMS.meeting(
        "https://teams.microsoft.com/l/chat/0/0",
        "Möte om ÅÄÖ och en mycket lång titel som fortsätter | Teams",
    )
    assert ref is not None
    assert ref.code.startswith("title:mote-om-aao")
    assert len(ref.code.removeprefix("title:")) <= 40
    assert not ref.code.endswith("-")


def test_teams_untitled_fallback() -> None:
    ref = TEAMS.meeting("https://teams.microsoft.com/l/chat/0/0", "")
    assert ref is not None
    assert ref.code == "title:untitled"
    assert ref.title == "title:untitled"


@pytest.mark.parametrize(
    "url",
    [
        "https://teams.microsoft.com.evil.example/l/meetup-join/19:meeting_a@thread.v2",
        "https://meet.google.com/abc-defg-hij",
        "",
    ],
)
def test_not_a_teams_tab(url: str) -> None:
    assert TEAMS.meeting(url, "Weekly sync") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello, World!", "hello-world"),
        ("  Spaces   and   dashes  ", "spaces-and-dashes"),
        ("Möte om ÅÄÖ", "mote-om-aao"),
        ("", ""),
    ],
)
def test_slug(text: str, expected: str) -> None:
    assert slug(text) == expected


def test_slug_is_at_most_40_characters() -> None:
    assert slug("a" * 60) == "a" * 40


def test_poll_js_checks_the_class_name() -> None:
    assert "speaking-indicator" in MEET.poll_js("speaking-indicator")
    for bad in ("", "invalid class", "cls'; alert('xss');//", "a.b"):
        with pytest.raises(ValueError):
            MEET.poll_js(bad)
        with pytest.raises(ValueError):
            TEAMS.poll_js(bad)


def test_parse_rejects_bad_json() -> None:
    with pytest.raises(ValueError):
        MEET.parse_snapshot("not json")
    with pytest.raises(ValueError):
        MEET.parse_poll('{"name": "Alice"}')
    with pytest.raises(ValueError):
        TEAMS.parse_snapshot("not json")
    with pytest.raises(ValueError):
        TEAMS.parse_poll('{"name": "Alice"}')


def test_parse_skips_tiles_without_a_name() -> None:
    assert MEET.parse_snapshot('[{"name": "", "classes": ["x"]}]') == []
    assert MEET.parse_poll('[{"name": null, "speaking": true}]') == []
