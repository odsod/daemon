from __future__ import annotations

from odsod_daemon.components.signals.debounce import Change, SpeakerDebounce

POLL = 0.25


def tracker() -> SpeakerDebounce:
    return SpeakerDebounce(
        start_samples=2,
        start_window_s=1.5,
        stop_grace_s=2.0,
        poll_s=POLL,
    )


def test_one_flash_does_not_start_a_speaker() -> None:
    debounce = tracker()
    assert debounce.observe(0.0, ["Alice"]) == []
    assert debounce.observe(2.0, []) == []
    assert debounce.active == frozenset()


def test_two_samples_start_at_the_first_sample() -> None:
    debounce = tracker()
    assert debounce.observe(0.0, ["Alice"]) == []
    assert debounce.observe(0.75, ["Alice"]) == [Change("Alice", True, 0.0)]
    assert debounce.active == frozenset({"Alice"})


def test_short_dropout_holds_the_speaker() -> None:
    debounce = tracker()
    debounce.observe(0.0, ["Alice"])
    debounce.observe(0.5, ["Alice"])
    assert debounce.observe(1.5, []) == []
    assert debounce.active == frozenset({"Alice"})


def test_stop_after_grace_at_the_next_poll() -> None:
    debounce = tracker()
    debounce.observe(0.0, ["Alice"])
    debounce.observe(0.5, ["Alice"])
    assert debounce.observe(2.5, []) == []
    assert debounce.observe(2.75, []) == [Change("Alice", False, 0.5 + POLL)]
    assert debounce.active == frozenset()


def test_overlapping_speakers_start_together() -> None:
    debounce = tracker()
    debounce.observe(0.0, ["Alice", "Bob"])
    changes = debounce.observe(0.5, ["Alice", "Bob"])
    assert sorted(changes, key=lambda change: change.name) == [
        Change("Alice", True, 0.0),
        Change("Bob", True, 0.0),
    ]
    assert debounce.active == frozenset({"Alice", "Bob"})


def test_samples_outside_the_window_do_not_count() -> None:
    debounce = tracker()
    assert debounce.observe(0.0, ["Alice"]) == []
    assert debounce.observe(2.0, ["Alice"]) == []
    assert debounce.observe(2.25, ["Alice"]) == [Change("Alice", True, 2.0)]


def test_a_speaker_that_leaves_the_tiles_stops() -> None:
    debounce = tracker()
    debounce.observe(0.0, ["Alice"])
    debounce.observe(0.5, ["Alice"])
    assert debounce.observe(1.0, []) == []
    assert debounce.observe(3.0, []) == [Change("Alice", False, 0.5 + POLL)]


def test_resume_adopts_a_previous_set() -> None:
    debounce = tracker()
    debounce.resume(["Alice", "Bob"], 10.0)
    assert debounce.active == frozenset({"Alice", "Bob"})
    assert debounce.observe(10.25, []) == []
    changes = debounce.observe(13.0, [])
    assert sorted(changes, key=lambda change: change.name) == [
        Change("Alice", False, 10.0 + POLL),
        Change("Bob", False, 10.0 + POLL),
    ]


def test_reset_drops_every_speaker() -> None:
    debounce = tracker()
    debounce.resume(["Alice"], 0.0)
    debounce.reset()
    assert debounce.active == frozenset()


def test_empty_names_are_ignored() -> None:
    debounce = tracker()
    assert debounce.observe(0.0, ["", ""]) == []
    assert debounce.active == frozenset()
