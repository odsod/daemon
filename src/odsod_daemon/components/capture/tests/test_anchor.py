"""Table tests for the pure anchor (ADR-0011 "Block loop")."""

from __future__ import annotations

import pytest

from odsod_daemon.components.capture.anchor import (
    BLOCK_SECONDS,
    GAP_THRESHOLD_S,
    Anchor,
)


def _steady(anchor: Anchor, count: int, *, first: float = 100.0) -> list:
    placements = [anchor.place(first + index * BLOCK_SECONDS) for index in range(count)]
    assert anchor.t0 is not None
    return placements


def test_t0_is_first_arrival_minus_block_and_latency() -> None:
    anchor = Anchor(latency_ms=100)
    placement = anchor.place(100.0)
    assert anchor.t0 is not None
    assert anchor.t0 == pytest.approx(100.0 - BLOCK_SECONDS - 0.1)
    assert placement.start == pytest.approx(anchor.t0)
    assert placement.end == pytest.approx(anchor.t0 + BLOCK_SECONDS)
    assert placement.hole == 0.0


def test_steady_blocks_are_continuous_with_no_hole() -> None:
    anchor = Anchor()
    placements = _steady(anchor, 20)
    assert anchor.t0 is not None
    assert [placed.start for placed in placements] == pytest.approx(
        [anchor.t0 + index * BLOCK_SECONDS for index in range(20)]
    )
    assert all(placed.hole == 0.0 and not placed.dropped for placed in placements)


def test_50ppm_drift_over_a_day_stays_within_150ms() -> None:
    anchor = Anchor()
    seconds_per_block = BLOCK_SECONDS / (1 - 50e-6)
    written = 0
    worst = 0.0
    holes = 0
    for index in range(24 * 3600 * 10):
        arrival = (index + 1) * seconds_per_block
        placement = anchor.place(arrival)
        if placement.dropped:
            continue
        wall_start = arrival - BLOCK_SECONDS
        worst = max(worst, abs(placement.start - wall_start))
        if placement.hole > 0:
            holes += 1
            assert placement.hole < GAP_THRESHOLD_S
        written += 1
    assert written > 24 * 3600 * 9
    assert holes > 0
    assert worst <= 0.16


def test_forward_clock_step_leaves_one_gap_and_no_backward_write() -> None:
    anchor = Anchor()
    start = 0.0
    first = anchor.place(start + 0.1)
    second = anchor.place(start + 0.2)
    stepped = anchor.place(start + 1.3)
    assert stepped.hole == pytest.approx(1.0)
    assert stepped.hole >= GAP_THRESHOLD_S
    assert stepped.start == pytest.approx(0.2 + 1.0)
    assert stepped.start >= second.end
    following = anchor.place(start + 1.3)
    assert following.hole == 0.0
    assert following.start == pytest.approx(stepped.start + BLOCK_SECONDS)
    assert first.start == 0.0


def test_backward_clock_step_drops_blocks_and_never_writes_back() -> None:
    anchor = Anchor()
    anchor.place(0.1)
    kept = anchor.place(0.2)
    dropped = anchor.place(-0.7)
    assert dropped.dropped
    assert dropped.start == kept.end
    for arrival in (-0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3):
        placement = anchor.place(arrival)
        assert placement.dropped or placement.start >= kept.end
    resumed = anchor.place(0.4)
    assert not resumed.dropped
    assert resumed.start >= kept.end
    assert resumed.start == pytest.approx(kept.end)
    assert resumed.end == pytest.approx(resumed.start + BLOCK_SECONDS)


def test_latency_shifts_audio_but_keeps_steady_blocks_stable() -> None:
    anchor = Anchor(latency_ms=100)
    placements = _steady(anchor, 20)
    assert [placed.hole for placed in placements] == pytest.approx([0.0] * 20)
    assert anchor.t0 is not None
    assert placements[-1].start == pytest.approx(anchor.t0 + 19 * BLOCK_SECONDS)
