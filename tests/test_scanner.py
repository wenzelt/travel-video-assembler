"""Tests for travel_video.scanner — written FIRST (TDD Red phase)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from travel_video.scanner import scan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = [".mp4", ".mov", ".mkv", ".m4v"]
NON_VIDEO_EXTENSIONS = [".txt", ".jpg", ".png", ".pdf", ".avi", ".wav"]


def _touch(path: Path, mtime: float | None = None) -> Path:
    """Create an empty file and optionally set its mtime."""
    path.touch()
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# 1. Returns only video files (ignores non-video extensions)
# ---------------------------------------------------------------------------


def test_returns_only_video_files(tmp_path: Path) -> None:
    """scan() must include only recognised video extensions."""
    for ext in VIDEO_EXTENSIONS:
        _touch(tmp_path / f"clip{ext}")
    for ext in NON_VIDEO_EXTENSIONS:
        _touch(tmp_path / f"other{ext}")

    result = scan(tmp_path)

    result_exts = {p.suffix.lower() for p in result}
    assert result_exts == set(VIDEO_EXTENSIONS)


def test_ignores_non_video_files_entirely(tmp_path: Path) -> None:
    """scan() must return an empty list when only non-video files exist."""
    for ext in NON_VIDEO_EXTENSIONS:
        _touch(tmp_path / f"other{ext}")

    result = scan(tmp_path)

    assert result == []


# ---------------------------------------------------------------------------
# 2. Case-insensitive extension matching
# ---------------------------------------------------------------------------


def test_case_insensitive_mp4_uppercase(tmp_path: Path) -> None:
    video = _touch(tmp_path / "clip.MP4")
    result = scan(tmp_path)
    assert video in result


def test_case_insensitive_mov_uppercase(tmp_path: Path) -> None:
    video = _touch(tmp_path / "clip.MOV")
    result = scan(tmp_path)
    assert video in result


def test_case_insensitive_mixed_case(tmp_path: Path) -> None:
    videos = [
        _touch(tmp_path / "a.Mp4"),
        _touch(tmp_path / "b.mKv"),
        _touch(tmp_path / "c.M4V"),
    ]
    result = scan(tmp_path)
    assert set(result) == set(videos)


# ---------------------------------------------------------------------------
# 3. Sort order by mtime (creation time proxy in tests)
# ---------------------------------------------------------------------------


def test_sorted_by_mtime_ascending(tmp_path: Path) -> None:
    """Files must be returned sorted by creation/modification time, oldest first.

    On macOS, ``st_birthtime`` is used as the primary key.  Since ``st_birthtime``
    reflects real filesystem creation time and cannot be overridden via
    ``os.utime``, we create the files in the expected ascending order (a, b, c)
    and set their ``st_mtime`` to match that same ordering so the test is
    consistent on both macOS (birthtime) and other platforms (mtime).
    """
    base = time.time()
    # Create files in intended sort order so st_birthtime is also ascending.
    a = _touch(tmp_path / "a.mp4", mtime=base + 0)
    b = _touch(tmp_path / "b.mp4", mtime=base + 100)
    c = _touch(tmp_path / "c.mp4", mtime=base + 200)

    result = scan(tmp_path)

    assert result == [a, b, c]


def test_sorted_by_mtime_single_file(tmp_path: Path) -> None:
    """Single file must be returned in a one-element list."""
    video = _touch(tmp_path / "only.mp4")
    result = scan(tmp_path)
    assert result == [video]


def test_sorted_order_is_stable_for_equal_mtimes(tmp_path: Path) -> None:
    """Files with identical mtimes must still all appear in the result."""
    base = time.time()
    videos = [_touch(tmp_path / f"v{i}.mp4", mtime=base) for i in range(3)]

    result = scan(tmp_path)

    assert set(result) == set(videos)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# 4. Returns empty list for an empty directory
# ---------------------------------------------------------------------------


def test_empty_directory_returns_empty_list(tmp_path: Path) -> None:
    result = scan(tmp_path)
    assert result == []


# ---------------------------------------------------------------------------
# 5. FileNotFoundError for missing directory
# ---------------------------------------------------------------------------


def test_missing_directory_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        scan(missing)


# ---------------------------------------------------------------------------
# 6. NotADirectoryError for a file path
# ---------------------------------------------------------------------------


def test_file_path_raises_not_a_directory(tmp_path: Path) -> None:
    a_file = _touch(tmp_path / "not_a_dir.mp4")
    with pytest.raises(NotADirectoryError):
        scan(a_file)


# ---------------------------------------------------------------------------
# 7. Recursive walk (nested sub-directories)
# ---------------------------------------------------------------------------


def test_walks_subdirectories_recursively(tmp_path: Path) -> None:
    sub = tmp_path / "sub" / "deep"
    sub.mkdir(parents=True)
    top = _touch(tmp_path / "top.mp4")
    nested = _touch(sub / "nested.mp4")

    result = scan(tmp_path)

    assert top in result
    assert nested in result
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 8. Return value is a new list (immutability — do not mutate caller state)
# ---------------------------------------------------------------------------


def test_returns_new_list_not_mutation(tmp_path: Path) -> None:
    _touch(tmp_path / "clip.mp4")
    result1 = scan(tmp_path)
    result2 = scan(tmp_path)
    assert result1 is not result2
