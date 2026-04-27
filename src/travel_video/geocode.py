"""geocode.py — reverse-geocode GPS coordinates to a Location using geopy/Nominatim.

Results are cached in ``<cache_root>/metadata/geocode.json`` keyed by
``"<round(lat,4)>,<round(lon,4)>"`` (≈11 m precision).  Only successful
lookups are cached; errors and None results are not stored.

Rate-limiting: geopy's ``RateLimiter`` enforces a minimum 1 s delay between
requests so that Nominatim's usage policy is respected.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_TOWN_KEYS = ("city", "town", "village", "hamlet", "county")


@dataclass(frozen=True)
class Location:
    """A reverse-geocoded place."""

    town: str
    country: str
    iso: str  # ISO 3166-1 alpha-2 country code (upper-case)


# ---------------------------------------------------------------------------
# Internal cache helpers
# ---------------------------------------------------------------------------


def _cache_root() -> Path:
    """Return the cache root directory.

    Uses ``TRAVEL_VIDEO_CACHE_DIR`` env var when set; falls back to
    ``.travel_video_cache/`` relative to the current working directory.
    """
    env_val = os.environ.get("TRAVEL_VIDEO_CACHE_DIR")
    if env_val:
        return Path(env_val)
    return Path.cwd() / ".travel_video_cache"


def _geocode_cache_path() -> Path:
    """Return the path to ``geocode.json``, creating the metadata dir if needed."""
    meta_dir = _cache_root() / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    return meta_dir / "geocode.json"


def _load_cache() -> dict[str, dict]:
    """Load the geocode cache from disk, returning an empty dict on any error."""
    path = _geocode_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(data: dict[str, dict]) -> None:
    """Write *data* to the geocode cache file."""
    path = _geocode_cache_path()
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reverse(
    lat: float | None,
    lon: float | None,
    *,
    user_agent: str = "travel-video-assembler",
) -> Location | None:
    """Reverse-geocode *lat*/*lon* to a :class:`Location`.

    Returns ``None`` immediately when either coordinate is ``None``.
    Returns ``None`` on network error, geocoder failure, or when the
    location cannot be resolved to a place name.

    Successful results are cached in ``<cache_root>/metadata/geocode.json``
    keyed by ``f"{round(lat, 4)},{round(lon, 4)}"``.  Subsequent calls with
    the same (rounded) coordinates are served from the cache without
    contacting Nominatim.

    Args:
        lat:        WGS-84 latitude in decimal degrees, or ``None``.
        lon:        WGS-84 longitude in decimal degrees, or ``None``.
        user_agent: User-agent string forwarded to Nominatim (required by
                    the Nominatim usage policy).

    Returns:
        A :class:`Location` on success, or ``None``.
    """
    if lat is None or lon is None:
        return None

    cache_key = f"{round(lat, 4)},{round(lon, 4)}"

    # --- Cache lookup ---
    cache = _load_cache()
    if cache_key in cache:
        entry = cache[cache_key]
        return Location(town=entry["town"], country=entry["country"], iso=entry["iso"])

    # --- Live geocode ---
    try:
        geocoder_instance = Nominatim(user_agent=user_agent)
        geocoder = RateLimiter(geocoder_instance.reverse, min_delay_seconds=1)
        location = geocoder(f"{lat},{lon}", language="en")

        if location is None:
            return None

        address: dict = location.raw["address"]
        town: str | None = None
        for key in _TOWN_KEYS:
            if key in address:
                town = address[key]
                break

        if town is None:
            return None

        country: str = address["country"]
        iso: str = address["country_code"].upper()

    except Exception:  # noqa: BLE001
        return None

    # --- Persist to cache ---
    cache[cache_key] = {"town": town, "country": country, "iso": iso}
    _save_cache(cache)

    return Location(town=town, country=country, iso=iso)
