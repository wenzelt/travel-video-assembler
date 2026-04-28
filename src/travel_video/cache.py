"""cache.py — stable file-version keys and cache read/write helpers.

Cache root: ``.travel_video_cache/`` (relative to cwd), or the directory
specified by the ``TRAVEL_VIDEO_CACHE_DIR`` environment variable.

Sub-directories
---------------
metadata/   — per-clip metadata as JSON files
maps/       — map tile PNG files
normalized/ — normalised clip MKV files
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Internal helpers
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


def _ensure(subdir: str) -> Path:
    """Return ``<cache_root>/<subdir>/``, creating it if needed."""
    path = _cache_root() / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cache_key(path: Path) -> str:
    """Return a SHA-1 hex digest that is stable for a specific file version.

    The digest is computed from ``"<absolute_path>:<mtime_ns>"`` so it
    changes whenever the file is modified and differs for files at different
    paths even when they share the same mtime.

    Args:
        path: Path to the file whose cache key is needed.

    Returns:
        A 40-character lowercase hex string.
    """
    abs_path = str(path.resolve())
    mtime_ns = path.stat().st_mtime_ns
    raw = f"{abs_path}:{mtime_ns}"
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()


def _validate_key(key: str) -> None:
    """Ensure key is a safe string for use as a filename.
    
    Prevents path traversal by forbidding slashes, backslashes, and '..'.
    Allows alphanumeric characters, underscores, dots, and hyphens.
    """
    if not isinstance(key, str):
        raise ValueError(f"Cache key must be a string, got {type(key).__name__}")
    
    if not key or key in (".", "..") or "/" in key or "\\" in key or ".." in key:
        raise ValueError(f"Invalid or unsafe cache key: {key!r}")
    
    # Allow alphanumeric, underscore, dot, hyphen
    if not all(c.isalnum() or c in "_.-" for c in key):
        raise ValueError(f"Invalid characters in cache key: {key!r}")


def metadata_cache_get(key: str) -> dict | None:
    """Return the cached metadata dict for *key*, or ``None`` if not present.

    Treats corrupted or unreadable cache files as a cache miss rather than
    raising an exception.

    Args:
        key: Cache key as returned by :func:`cache_key`.

    Returns:
        The previously stored dict, or ``None`` when there is no entry.
    """
    try:
        _validate_key(key)
    except ValueError:
        return None

    # Intentionally does not call _ensure() — a read must not create the directory.
    cache_file = _cache_root() / "metadata" / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def metadata_cache_set(key: str, data: dict) -> None:
    """Write *data* to the metadata cache under *key*.

    Creates the ``metadata/`` subdirectory if it does not exist.

    Args:
        key:  Cache key as returned by :func:`cache_key`.
        data: Arbitrary JSON-serialisable dict to store.
    """
    _validate_key(key)
    meta_dir = _ensure("metadata")
    cache_file = meta_dir / f"{key}.json"
    
    tmp = cache_file.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, cache_file)
    except OSError:
        if tmp.exists():
            tmp.unlink()
        raise


def normalized_path(key: str) -> Path:
    """Return the expected filesystem path for a normalised clip MKV.

    The ``normalized/`` subdirectory is created automatically if absent.

    Args:
        key: Cache key as returned by :func:`cache_key`.

    Returns:
        A :class:`~pathlib.Path` of the form ``<cache_root>/normalized/<key>.mkv``.
    """
    _validate_key(key)
    norm_dir = _ensure("normalized")
    return norm_dir / f"{key}.mkv"


def map_path(key: str) -> Path:
    """Return the expected filesystem path for a cached map PNG.

    The ``maps/`` subdirectory is created automatically if absent.

    Args:
        key: Cache key as returned by :func:`cache_key`.

    Returns:
        A :class:`~pathlib.Path` of the form ``<cache_root>/maps/<key>.png``.
    """
    _validate_key(key)
    maps_dir = _ensure("maps")
    return maps_dir / f"{key}.png"
