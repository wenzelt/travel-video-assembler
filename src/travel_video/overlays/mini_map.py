"""mini_map.py — static OSM map tile overlay for a clip.

Fetches a 320×320 PNG from OpenStreetMap's static-map service, caches it
locally, and returns an FFmpeg overlay filter fragment positioning the map
in the top-right corner.

The decision of whether to show the map for a given clip is deterministic:
it is based on a hash of the clip path, so the same clip always gets the
same answer across runs.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from travel_video import cache
from travel_video.config import Config
from travel_video.models import Clip

_OSM_URL = (
    "https://staticmap.openstreetmap.de/staticmap.php"
    "?center={lat},{lon}&zoom=13&size=320x320"
)
_MAP_SIZE = 320
_MARGIN = 48


def should_show(clip: Clip, *, probability: float = 0.25) -> bool:
    """Deterministic probability check based on the clip's path hash.

    Uses ``hash(str(clip.path)) % 100 < int(probability * 100)`` so the
    same clip always produces the same decision regardless of run order.

    Args:
        clip:        The clip to evaluate.
        probability: Fraction in [0.0, 1.0] of clips that show the map.

    Returns:
        ``True`` when the map should be shown for this clip.
    """
    return hash(str(clip.path)) % 100 < int(probability * 100)


def build(clip: Clip, config: Config) -> tuple[Path, str] | None:  # noqa: ARG002
    """Fetch (or reuse cached) OSM map PNG and return overlay filter fragment.

    Returns ``None`` when:
    - The clip has no GPS coordinates.
    - :func:`should_show` returns ``False`` for the clip.
    - The PNG fetch raises any exception.

    The PNG is cached at ``cache.map_path(cache.cache_key(clip.path))``.
    If the file already exists the network fetch is skipped.

    Args:
        clip:   The source clip providing GPS coordinates and path key.
        config: Project configuration (reserved for future use).

    Returns:
        ``(png_path, overlay_fragment)`` on success, or ``None``.
    """
    if clip.gps_lat is None or clip.gps_lon is None:
        return None

    if not should_show(clip, probability=config.overlays.mini_map.probability):
        return None

    key = cache.cache_key(clip.path)
    png_path = cache.map_path(key)

    if not png_path.exists():
        url = _OSM_URL.format(lat=clip.gps_lat, lon=clip.gps_lon)
        try:
            urllib.request.urlretrieve(url, str(png_path))
        except Exception:  # noqa: BLE001
            return None

    fragment = f"overlay=W-w-{_MARGIN}:{_MARGIN}"
    return png_path, fragment
