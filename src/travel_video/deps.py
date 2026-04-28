"""Runtime dependency checks for FFmpeg and ExifTool."""

from __future__ import annotations

import shutil
import sys


def check_dependencies() -> None:
    """Verify ffmpeg and exiftool are on PATH. Exit with a friendly message if not."""
    missing = [tool for tool in ("ffmpeg", "exiftool") if shutil.which(tool) is None]
    if missing:
        tools_str = " and ".join(missing)
        sys.exit(
            f"Error: {tools_str} not found on PATH.\n"
            f"Install with: brew install {' '.join(missing)}"
        )
