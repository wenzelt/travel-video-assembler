"""metadata.py — extract Clip metadata from video files via ExifTool.

Shells out to ``exiftool -j`` and parses the JSON result.  Results are cached
in the metadata cache so repeated calls for the same file version are instant.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from travel_video import cache
from travel_video.models import Clip

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EXIFTOOL_FIELDS = [
    "-CreateDate",
    "-MediaCreateDate",
    "-TrackCreateDate",
    "-QuickTime:CreateDate",
    "-GPSLatitude",
    "-GPSLongitude",
    "-Rotation",
    "-Composite:Rotation",
    "-Duration",
    "-DurationValue",
    "-ImageWidth",
    "-ImageHeight",
]

_DATE_FMT = "%Y:%m:%d %H:%M:%S"

# Matches "48.8584 N", "2.2945 E", "33.8688 S", "151.2093 W"
_SIMPLE_DIRECTIONAL = re.compile(
    r"^\s*(?P<value>[\d.]+)\s+(?P<dir>[NSEWnsew])\s*$"
)

# Matches "48 deg 51' 30.24\" N"
_DMS = re.compile(
    r"""^\s*
        (?P<deg>\d+)\s+deg\s+
        (?P<min>\d+)['′]\s+
        (?P<sec>[\d.]+)[\"″]\s+
        (?P<dir>[NSEWnsew])
    \s*$""",
    re.VERBOSE,
)


def extract(path: Path) -> Clip:
    """Extract metadata from a video file and return a :class:`~travel_video.models.Clip`.

    Shells out to ``exiftool -j``, parses the JSON output.
    Falls back to ``st_mtime`` for ``creation_time`` when no EXIF date is present.
    Results are cached via :mod:`travel_video.cache`.

    Args:
        path: Absolute or relative path to the video file.

    Returns:
        A populated :class:`~travel_video.models.Clip`.

    Raises:
        RuntimeError: When ``exiftool`` exits with a non-zero return code.
    """
    key = cache.cache_key(path)

    cached = cache.metadata_cache_get(key)
    if cached is not None:
        return _clip_from_dict(path, cached)

    raw = _run_exiftool(path)
    clip = _parse(path, raw)

    cache.metadata_cache_set(key, _clip_to_dict(clip))
    return clip


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_exiftool(path: Path) -> dict:
    """Invoke exiftool and return the first record as a dict.

    Raises:
        RuntimeError: On non-zero exit code.
    """
    cmd = ["exiftool", "-j", *_EXIFTOOL_FIELDS, str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        raise RuntimeError(
            f"exiftool failed (exit {result.returncode}) for {path}: {result.stderr}"
        )
    records = json.loads(result.stdout)
    return records[0] if records else {}


def _parse(path: Path, tags: dict) -> Clip:
    """Build a :class:`Clip` from an ExifTool tag dict."""
    return Clip(
        path=path,
        duration_s=_parse_duration(tags),
        creation_time=_parse_creation_time(path, tags),
        gps_lat=_parse_gps(tags.get("GPSLatitude"), is_lat=True),
        gps_lon=_parse_gps(tags.get("GPSLongitude"), is_lat=False),
        rotation=_parse_rotation(tags),
        width=int(tags.get("ImageWidth", 0)),
        height=int(tags.get("ImageHeight", 0)),
    )


# --------------- creation_time -------------------------------------------


def _parse_creation_time(path: Path, tags: dict) -> datetime:
    """Return the first valid EXIF date, or fall back to file mtime."""
    for field in ("CreateDate", "MediaCreateDate", "TrackCreateDate", "QuickTime:CreateDate"):
        raw = tags.get(field)
        if raw:
            try:
                return datetime.strptime(raw, _DATE_FMT)
            except (ValueError, TypeError):
                continue
    return datetime.fromtimestamp(path.stat().st_mtime)


# --------------- duration -------------------------------------------------


def _parse_duration(tags: dict) -> float:
    """Return duration in seconds as a float.

    Handles:
    - A numeric value (int or float)
    - A time string like ``"0:01:23"`` or ``"1:23:45.67"``
    """
    raw = tags.get("Duration") or tags.get("DurationValue")
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return _parse_duration_string(str(raw))


def _parse_duration_string(s: str) -> float:
    """Convert ``"H:MM:SS.ss"`` or ``"M:SS"`` to seconds."""
    parts = s.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = parts
            return float(h) * 3600 + float(m) * 60 + float(sec)
        if len(parts) == 2:
            m, sec = parts
            return float(m) * 60 + float(sec)
        return float(s)
    except ValueError:
        return 0.0


# --------------- GPS ------------------------------------------------------


def _parse_gps(raw: float | str | None, *, is_lat: bool) -> float | None:  # noqa: ARG001
    """Parse a GPS value that may be a float or a directional string.

    Returns ``None`` when the value is absent or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()

    # Try DMS first (more specific pattern)
    m = _DMS.match(s)
    if m:
        decimal = (
            float(m.group("deg"))
            + float(m.group("min")) / 60
            + float(m.group("sec")) / 3600
        )
        if m.group("dir").upper() in ("S", "W"):
            decimal = -decimal
        return decimal

    # Try simple decimal + direction
    m = _SIMPLE_DIRECTIONAL.match(s)
    if m:
        decimal = float(m.group("value"))
        if m.group("dir").upper() in ("S", "W"):
            decimal = -decimal
        return decimal

    # Last resort: try bare float string
    try:
        return float(s)
    except ValueError:
        return None


# --------------- rotation -------------------------------------------------


def _parse_rotation(tags: dict) -> int:
    """Return rotation from Rotation, then Composite:Rotation, then 0."""
    for field in ("Rotation", "Composite:Rotation"):
        raw = tags.get(field)
        if raw is not None:
            try:
                return int(raw)
            except (ValueError, TypeError):
                continue
    return 0


# --------------- cache serialisation ------------------------------------


def _clip_to_dict(clip: Clip) -> dict:
    """Convert a :class:`Clip` to a JSON-serialisable dict for caching."""
    return {
        "path": str(clip.path),
        "duration_s": clip.duration_s,
        "creation_time": clip.creation_time.strftime(_DATE_FMT),
        "gps_lat": clip.gps_lat,
        "gps_lon": clip.gps_lon,
        "rotation": clip.rotation,
        "width": clip.width,
        "height": clip.height,
    }


def _clip_from_dict(path: Path, data: dict) -> Clip:
    """Reconstruct a :class:`Clip` from a cached dict."""
    return Clip(
        path=path,
        duration_s=float(data["duration_s"]),
        creation_time=datetime.strptime(data["creation_time"], _DATE_FMT),
        gps_lat=data["gps_lat"],
        gps_lon=data["gps_lon"],
        rotation=int(data["rotation"]),
        width=int(data["width"]),
        height=int(data["height"]),
    )
