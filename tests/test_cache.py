"""Tests for travel_video.cache — written FIRST (TDD Red phase)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from travel_video.cache import (
    cache_key,
    map_path,
    metadata_cache_get,
    metadata_cache_set,
    normalized_path,
)

# ---------------------------------------------------------------------------
# 1. cache_key is deterministic for the same path + mtime
# ---------------------------------------------------------------------------


def test_cache_key_deterministic(tmp_path: Path) -> None:
    """cache_key() must return the same value for identical path + mtime."""
    f = tmp_path / "clip.mp4"
    f.touch()
    key1 = cache_key(f)
    key2 = cache_key(f)
    assert key1 == key2


def test_cache_key_is_string(tmp_path: Path) -> None:
    """cache_key() must return a str."""
    f = tmp_path / "clip.mp4"
    f.touch()
    assert isinstance(cache_key(f), str)


def test_cache_key_non_empty(tmp_path: Path) -> None:
    """cache_key() must return a non-empty string."""
    f = tmp_path / "clip.mp4"
    f.touch()
    assert len(cache_key(f)) > 0


# ---------------------------------------------------------------------------
# 2. cache_key changes when mtime changes
# ---------------------------------------------------------------------------


def test_cache_key_changes_with_mtime(tmp_path: Path) -> None:
    """cache_key() must differ after the file's mtime is updated."""
    f = tmp_path / "clip.mp4"
    f.touch()
    os.utime(f, (1_000_000, 1_000_000))
    key_before = cache_key(f)

    os.utime(f, (2_000_000, 2_000_000))
    key_after = cache_key(f)

    assert key_before != key_after


def test_cache_key_different_paths_same_mtime_differ(tmp_path: Path) -> None:
    """Two files at different paths with the same mtime must have different keys."""
    mtime = 1_234_567_890.0
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.touch()
    b.touch()
    os.utime(a, (mtime, mtime))
    os.utime(b, (mtime, mtime))

    assert cache_key(a) != cache_key(b)


# ---------------------------------------------------------------------------
# 3. metadata_cache_get returns None for uncached key
# ---------------------------------------------------------------------------


def test_metadata_cache_get_miss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """metadata_cache_get() returns None when the key is not cached."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    result = metadata_cache_get("nonexistent_key")
    assert result is None


def test_metadata_cache_get_miss_returns_none_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return value must be exactly None, not a falsy empty dict."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    result = metadata_cache_get("another_missing_key")
    assert result is None


# ---------------------------------------------------------------------------
# 4. metadata_cache_set then metadata_cache_get round-trips data
# ---------------------------------------------------------------------------


def test_metadata_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """set followed by get must return the same dict."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    data = {"duration": 12.5, "width": 1920, "height": 1080}
    metadata_cache_set("round_trip_key", data)
    result = metadata_cache_get("round_trip_key")
    assert result == data


def test_metadata_round_trip_complex_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Round-trip must preserve nested structures, lists, and None values."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    data = {
        "gps_lat": None,
        "gps_lon": None,
        "tags": ["travel", "sunset"],
        "nested": {"key": "value"},
        "rotation": 90,
    }
    metadata_cache_set("complex_key", data)
    result = metadata_cache_get("complex_key")
    assert result == data


def test_metadata_set_overwrites_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second set for the same key must overwrite the previous value."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    metadata_cache_set("overwrite_key", {"v": 1})
    metadata_cache_set("overwrite_key", {"v": 2})
    result = metadata_cache_get("overwrite_key")
    assert result == {"v": 2}


def test_metadata_cache_file_is_valid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The file written by metadata_cache_set must be valid JSON."""
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    metadata_cache_set("json_check_key", {"hello": "world"})

    meta_dir = cache_root / "metadata"
    json_files = list(meta_dir.glob("*.json"))
    assert len(json_files) == 1

    content = json.loads(json_files[0].read_text())
    assert content == {"hello": "world"}


# ---------------------------------------------------------------------------
# 5. normalized_path and map_path return paths under correct subdirs
# ---------------------------------------------------------------------------


def test_normalized_path_is_under_normalized_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """normalized_path() must return a path inside <cache_root>/normalized/."""
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    p = normalized_path("somekey")
    assert p.parts[-2] == "normalized"


def test_normalized_path_has_mkv_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """normalized_path() must return a .mkv path."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    p = normalized_path("somekey")
    assert p.suffix == ".mkv"


def test_map_path_is_under_maps_subdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """map_path() must return a path inside <cache_root>/maps/."""
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    p = map_path("somekey")
    assert p.parts[-2] == "maps"


def test_map_path_has_png_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """map_path() must return a .png path."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    p = map_path("somekey")
    assert p.suffix == ".png"


def test_path_functions_incorporate_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The key must appear in the filename returned by both path functions."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))
    key = "unique_test_key_abc123"
    assert key in normalized_path(key).name
    assert key in map_path(key).name


# ---------------------------------------------------------------------------
# 6. Cache dirs are auto-created on first use
# ---------------------------------------------------------------------------


def test_metadata_dirs_created_on_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """metadata_cache_set() must create the metadata subdir if it does not exist."""
    cache_root = tmp_path / "new_cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    assert not cache_root.exists()

    metadata_cache_set("auto_create_key", {"x": 1})

    assert (cache_root / "metadata").is_dir()


def test_metadata_dirs_created_on_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """metadata_cache_get() must not raise even if cache dir does not exist yet."""
    cache_root = tmp_path / "new_cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    assert not cache_root.exists()

    result = metadata_cache_get("missing_key_no_dir")
    assert result is None


def test_normalized_path_dir_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """normalized_path() must ensure <cache_root>/normalized/ exists."""
    cache_root = tmp_path / "new_cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    normalized_path("somekey")
    assert (cache_root / "normalized").is_dir()


def test_map_path_dir_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """map_path() must ensure <cache_root>/maps/ exists."""
    cache_root = tmp_path / "new_cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache_root))
    map_path("somekey")
    assert (cache_root / "maps").is_dir()


# ---------------------------------------------------------------------------
# 7. TRAVEL_VIDEO_CACHE_DIR env var controls root location
# ---------------------------------------------------------------------------


def test_env_var_sets_custom_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When TRAVEL_VIDEO_CACHE_DIR is set, that directory is used as cache root."""
    custom_root = tmp_path / "my_custom_cache"
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(custom_root))

    metadata_cache_set("env_var_key", {"a": 1})

    assert (custom_root / "metadata").is_dir()
    result = metadata_cache_get("env_var_key")
    assert result == {"a": 1}


def test_env_var_different_dirs_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Data written under one cache root must not be visible under another."""
    root_a = tmp_path / "cache_a"
    root_b = tmp_path / "cache_b"

    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(root_a))
    metadata_cache_set("shared_key", {"source": "a"})

    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(root_b))
    result = metadata_cache_get("shared_key")
    assert result is None


def test_default_cache_dir_without_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the env var, cache root defaults to .travel_video_cache/ relative to cwd."""
    monkeypatch.delenv("TRAVEL_VIDEO_CACHE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    metadata_cache_set("default_dir_key", {"default": True})

    assert (tmp_path / ".travel_video_cache" / "metadata").is_dir()
    result = metadata_cache_get("default_dir_key")
    assert result == {"default": True}
