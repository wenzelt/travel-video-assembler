"""day_separator.py — filtergraph for the 3-second black day-separator screen.

Wraps ffmpeg.filters.black_screen with dimensions and duration taken from
the project Config.
"""

from __future__ import annotations

from travel_video.config import Config
from travel_video.ffmpeg.filters import black_screen
from travel_video.models import DaySeparator


def build(sep: DaySeparator, config: Config) -> str:  # noqa: ARG001
    """Return a filtergraph string for a black day-separator screen.

    Duration and output dimensions are read from *config*.

    Args:
        sep:    The day-separator sentinel (carries the calendar date).
        config: Project configuration supplying duration and output size.

    Returns:
        An FFmpeg filtergraph fragment that generates a silent black screen.
    """
    return black_screen(
        duration_s=config.transitions.day_break_seconds,
        width=config.output.width,
        height=config.output.height,
    )
