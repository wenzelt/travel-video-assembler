"""location_label.py — FFmpeg drawtext overlay for reverse-geocoded location.

Renders "Town, Country, ISO" text in the bottom-right corner of a clip.
Returns None when GPS data is unavailable or geocoding fails.
"""

from __future__ import annotations

from travel_video.geocode import reverse
from travel_video.models import Clip


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter.

    Order matters: backslash must be escaped first so that later
    replacements don't double-escape already-escaped characters.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    return text


def build(clip: Clip, *, margin: int = 48) -> str | None:
    """Return an FFmpeg drawtext filtergraph fragment, or None if no GPS.

    Format: "Town, Country, ISO"
    Position: bottom-right with *margin* px from edges
    Style: white text, semi-transparent black box

    Args:
        clip:   The source clip whose GPS coordinates are used.
        margin: Pixel distance from the right and bottom edges.

    Returns:
        A drawtext filter fragment string, or ``None`` when GPS is absent
        or reverse-geocoding returns no result.
    """
    if clip.gps_lat is None or clip.gps_lon is None:
        return None

    location = reverse(clip.gps_lat, clip.gps_lon)
    if location is None:
        return None

    label = f"{location.town}, {location.country}, {location.iso}"
    escaped = _escape_drawtext(label)

    return (
        f"drawtext=text='{escaped}'"
        f":x=w-tw-{margin}:y=h-th-{margin}"
        f":fontsize=42:fontcolor=white"
        f":box=1:boxcolor=black@0.5:boxborderw=12"
    )
