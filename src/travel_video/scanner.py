"""scanner.py — walk an input directory and return sorted video file paths."""

from __future__ import annotations

from pathlib import Path

VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".mov", ".mkv", ".m4v"})


def _sort_key(path: Path) -> float:
    """Return a creation-time sort key for *path*.

    Uses ``st_birthtime`` (macOS creation time) when available; falls back to
    ``st_mtime`` (modification time) on filesystems that do not expose
    ``st_birthtime``.
    """
    stat = path.stat()
    return getattr(stat, "st_birthtime", None) or stat.st_mtime


def scan(input_dir: Path) -> list[Path]:
    """Walk *input_dir* recursively and return video files sorted by creation time.

    Args:
        input_dir: Directory to search for video files.

    Returns:
        A new list of :class:`~pathlib.Path` objects whose suffix (lowercased)
        is one of ``.mp4``, ``.mov``, ``.mkv``, or ``.m4v``, ordered from
        oldest to newest creation time.

    Raises:
        FileNotFoundError: If *input_dir* does not exist.
        NotADirectoryError: If *input_dir* exists but is not a directory.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    video_files = [
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]

    return sorted(video_files, key=_sort_key)
