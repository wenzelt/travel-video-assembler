"""Tests for travel_video.deps."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from travel_video.deps import check_dependencies


@pytest.mark.unit
def test_check_dependencies_passes_when_all_present() -> None:
    """No SystemExit when both ffmpeg and exiftool are found."""
    with patch("shutil.which", return_value="/usr/local/bin/ffmpeg"):
        check_dependencies()  # must not raise


@pytest.mark.unit
def test_check_dependencies_exits_when_ffmpeg_missing() -> None:
    """SystemExit when ffmpeg is not on PATH."""

    def which_side_effect(tool: str) -> str | None:
        return None if tool == "ffmpeg" else f"/usr/local/bin/{tool}"

    with patch("shutil.which", side_effect=which_side_effect), pytest.raises(
        SystemExit
    ) as exc_info:
        check_dependencies()
    assert "ffmpeg" in str(exc_info.value)


@pytest.mark.unit
def test_check_dependencies_exits_when_exiftool_missing() -> None:
    """SystemExit when exiftool is not on PATH."""

    def which_side_effect(tool: str) -> str | None:
        return None if tool == "exiftool" else f"/usr/local/bin/{tool}"

    with patch("shutil.which", side_effect=which_side_effect), pytest.raises(
        SystemExit
    ) as exc_info:
        check_dependencies()
    assert "exiftool" in str(exc_info.value)


@pytest.mark.unit
def test_check_dependencies_exits_when_both_missing() -> None:
    """SystemExit when both tools are missing."""
    with patch("shutil.which", return_value=None), pytest.raises(
        SystemExit
    ) as exc_info:
        check_dependencies()
    assert "ffmpeg" in str(exc_info.value)
    assert "exiftool" in str(exc_info.value)
