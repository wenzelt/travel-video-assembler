"""planner — groups Clip objects by calendar date and inserts DaySeparators."""

from __future__ import annotations

from travel_video.models import Clip, DaySeparator, TimelineItem


def build_timeline(clips: list[Clip]) -> list[TimelineItem]:
    """Group clips by calendar date, insert DaySeparator between day groups.

    - Clips are already sorted by creation_time (caller ensures this)
    - DaySeparator is inserted BETWEEN days — NOT before the first day
    - Preserves clip order within each day
    - Does NOT mutate the input list
    - Returns a new list
    """
    if not clips:
        return []

    result: list[TimelineItem] = []
    current_date = clips[0].creation_time.date()

    for clip in clips:
        clip_date = clip.creation_time.date()
        if clip_date != current_date:
            result.append(DaySeparator(date=clip_date))
            current_date = clip_date
        result.append(clip)

    return result
