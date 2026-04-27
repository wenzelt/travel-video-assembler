"""Tests for travel_video.planner — written FIRST (TDD Red phase)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from travel_video.models import Clip, DaySeparator
from travel_video.planner import build_timeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_PATH = Path("/dev/null")


def _clip(year: int, month: int, day: int, hour: int = 0) -> Clip:
    """Create a Clip with a fixed creation_time and dummy values for all other fields."""
    return Clip(
        path=_DUMMY_PATH,
        duration_s=5.0,
        creation_time=datetime(year, month, day, hour, 0, 0),
        gps_lat=None,
        gps_lon=None,
        rotation=0,
        width=1920,
        height=1080,
    )


# ---------------------------------------------------------------------------
# 1. Single day — no DaySeparator inserted
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_single_day_no_separator() -> None:
    """A list of clips all on the same day produces no DaySeparator."""
    clips = [_clip(2024, 7, 1, 8), _clip(2024, 7, 1, 10), _clip(2024, 7, 1, 14)]

    result = build_timeline(clips)

    assert result == clips
    assert not any(isinstance(item, DaySeparator) for item in result)


# ---------------------------------------------------------------------------
# 2. Two distinct days — exactly one DaySeparator between them
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_two_days_one_separator() -> None:
    """Two days produce exactly one DaySeparator between them."""
    day1_clip = _clip(2024, 7, 1)
    day2_clip = _clip(2024, 7, 2)

    result = build_timeline([day1_clip, day2_clip])

    assert len(result) == 3
    assert result[0] is day1_clip
    assert isinstance(result[1], DaySeparator)
    assert result[1].date == day2_clip.creation_time.date()
    assert result[2] is day2_clip


# ---------------------------------------------------------------------------
# 3. Three distinct days — two DaySeparators
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_three_days_two_separators() -> None:
    """Three days produce exactly two DaySeparators."""
    c1 = _clip(2024, 7, 1)
    c2 = _clip(2024, 7, 2)
    c3 = _clip(2024, 7, 3)

    result = build_timeline([c1, c2, c3])

    assert len(result) == 5
    assert result[0] is c1
    assert isinstance(result[1], DaySeparator)
    assert result[1].date == c2.creation_time.date()
    assert result[2] is c2
    assert isinstance(result[3], DaySeparator)
    assert result[3].date == c3.creation_time.date()
    assert result[4] is c3


# ---------------------------------------------------------------------------
# 4. Multiple clips per day — all preserved in order
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_multiple_clips_per_day_preserved_in_order() -> None:
    """Clips within the same day stay in their original order."""
    c1 = _clip(2024, 7, 1, 8)
    c2 = _clip(2024, 7, 1, 10)
    c3 = _clip(2024, 7, 1, 12)
    c4 = _clip(2024, 7, 2, 9)
    c5 = _clip(2024, 7, 2, 11)

    result = build_timeline([c1, c2, c3, c4, c5])

    assert len(result) == 6
    assert result[0] is c1
    assert result[1] is c2
    assert result[2] is c3
    assert isinstance(result[3], DaySeparator)
    assert result[3].date == c4.creation_time.date()
    assert result[4] is c4
    assert result[5] is c5


# ---------------------------------------------------------------------------
# 5. Empty input — returns empty list
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_input_returns_empty_list() -> None:
    """Empty input produces an empty list."""
    result = build_timeline([])

    assert result == []


# ---------------------------------------------------------------------------
# 6. Non-consecutive days (day 1, day 3 — day 2 missing) — one separator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_non_consecutive_days_one_separator_between_them() -> None:
    """A gap in the calendar still produces exactly one separator between the two day groups."""
    c1 = _clip(2024, 7, 1)
    c3 = _clip(2024, 7, 3)

    result = build_timeline([c1, c3])

    assert len(result) == 3
    assert result[0] is c1
    assert isinstance(result[1], DaySeparator)
    assert result[1].date == c3.creation_time.date()
    assert result[2] is c3


# ---------------------------------------------------------------------------
# 7. Input list is not mutated
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_input_list_not_mutated() -> None:
    """build_timeline must not modify the caller's list."""
    clips = [_clip(2024, 7, 1), _clip(2024, 7, 2)]
    original_ids = [id(c) for c in clips]
    original_length = len(clips)

    build_timeline(clips)

    assert len(clips) == original_length
    assert [id(c) for c in clips] == original_ids


# ---------------------------------------------------------------------------
# 8. DaySeparator is NOT inserted before the first day
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_separator_before_first_day() -> None:
    """The first item must always be a Clip, never a DaySeparator."""
    clips = [_clip(2024, 7, 1), _clip(2024, 7, 2), _clip(2024, 7, 3)]

    result = build_timeline(clips)

    assert isinstance(result[0], Clip)


# ---------------------------------------------------------------------------
# 9. Single clip — no separator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_single_clip_no_separator() -> None:
    """A single clip produces a one-element list with no DaySeparator."""
    c = _clip(2024, 7, 1)

    result = build_timeline([c])

    assert result == [c]
