"""Tests for the three overlay modules — updated for Pillow-based labels.

Covers:
- travel_video.overlays.location_label
- travel_video.overlays.day_separator
- travel_video.overlays.mini_map
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from travel_video.config import Config
from travel_video.geocode import Location
from travel_video.models import Clip, DaySeparator
from travel_video.overlays.day_separator import build as day_sep_build
from travel_video.overlays.location_label import build as label_build
from travel_video.overlays.mini_map import build as mini_map_build
from travel_video.overlays.mini_map import should_show

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_clip(
    *,
    path: str = "/tmp/clip.mp4",
    gps_lat: float | None = 48.8566,
    gps_lon: float | None = 2.3522,
) -> Clip:
    return Clip(
        path=Path(path),
        duration_s=5.0,
        creation_time=datetime(2024, 7, 1, 12, 0, 0),
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        rotation=0,
        width=1080,
        height=1920,
    )


# ---------------------------------------------------------------------------
# location_label tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_location_label_returns_none_when_no_gps() -> None:
    """build() returns None when the clip has no GPS coordinates."""
    clip = _make_clip(gps_lat=None, gps_lon=None)
    assert label_build(clip) is None


@pytest.mark.unit
def test_location_label_returns_tuple_for_gps_clip(tmp_path: Path) -> None:
    """build() returns (Path, str) for a GPS clip."""
    clip = _make_clip()
    with (
        patch("travel_video.overlays.location_label.reverse") as mock_reverse,
        patch("travel_video.overlays.location_label.cache") as mock_cache,
    ):
        mock_reverse.return_value = Location(town="Paris", country="France", iso="FR")
        fake_png = tmp_path / "label.png"
        mock_cache.map_path.return_value = fake_png
        mock_cache.cache_key.return_value = "key123"
        
        result = label_build(clip)

    assert result is not None
    png_path, fragment = result
    assert isinstance(png_path, Path)
    assert "overlay=" in fragment


@pytest.mark.unit
def test_location_label_returns_none_when_reverse_returns_none() -> None:
    """build() returns None when reverse() returns None (geocoding failed)."""
    clip = _make_clip()
    with patch("travel_video.overlays.location_label.reverse") as mock_reverse:
        mock_reverse.return_value = None
        result = label_build(clip)

    assert result is None


# ---------------------------------------------------------------------------
# day_separator tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_day_separator_contains_black_color() -> None:
    """build() returns a string containing 'color=c=black'."""
    sep = DaySeparator(date=date(2024, 7, 1))
    config = Config()
    result = day_sep_build(sep, config)

    assert "color=c=black" in result


@pytest.mark.unit
def test_day_separator_uses_duration_from_config() -> None:
    """build() reflects the day_break_seconds from config in the output."""
    sep = DaySeparator(date=date(2024, 7, 1))

    # Build a config with a custom day_break_seconds
    raw = yaml.safe_load("transitions:\n  day_break_seconds: 5.0\n")
    config = Config.model_validate(raw)

    result = day_sep_build(sep, config)

    assert "5.0" in result


# ---------------------------------------------------------------------------
# mini_map tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mini_map_should_show_consistent_for_same_clip() -> None:
    """should_show() returns the same result each time for the same clip path."""
    clip = _make_clip(path="/tmp/consistent_clip.mp4")
    first = should_show(clip)
    second = should_show(clip)
    assert first == second


@pytest.mark.unit
def test_mini_map_should_show_false_when_probability_zero() -> None:
    """should_show() always returns False when probability=0.0."""
    clip = _make_clip()
    assert should_show(clip, probability=0.0) is False


@pytest.mark.unit
def test_mini_map_should_show_true_when_probability_one() -> None:
    """should_show() always returns True when probability=1.0."""
    clip = _make_clip()
    assert should_show(clip, probability=1.0) is True


@pytest.mark.unit
def test_mini_map_build_returns_none_when_no_gps() -> None:
    """build() returns None when the clip has no GPS coordinates."""
    clip = _make_clip(gps_lat=None, gps_lon=None)
    config = Config()
    result = mini_map_build(clip, config)

    assert result is None


@pytest.mark.unit
def test_mini_map_build_returns_none_when_should_show_false() -> None:
    """build() returns None when should_show() returns False for the clip."""
    clip = _make_clip()
    config = Config()

    with patch("travel_video.overlays.mini_map.should_show") as mock_show:
        mock_show.return_value = False
        result = mini_map_build(clip, config)

    assert result is None


@pytest.mark.unit
def test_mini_map_build_returns_path_and_filter_when_successful(tmp_path: Path) -> None:
    """build() returns (Path, str) when GPS present, should_show is True, fetch succeeds."""
    clip = _make_clip()
    config = Config()

    def fake_urlopen(req, timeout=None):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = b"fake png data"
        resp.headers = {"Content-Type": "image/png"}
        return resp

    _patch_urlopen = "travel_video.overlays.mini_map.urllib.request.urlopen"
    with (
        patch("travel_video.overlays.mini_map.should_show") as mock_show,
        patch("travel_video.overlays.mini_map.cache") as mock_cache,
        patch(_patch_urlopen, side_effect=fake_urlopen),
        patch("travel_video.overlays.mini_map.urllib.request.Request") as mock_req,
    ):
        mock_show.return_value = True
        fake_png = tmp_path / "map.png"
        mock_cache.map_path.return_value = fake_png
        mock_cache.cache_key.return_value = "abc123"

        result = mini_map_build(clip, config)

    assert result is not None
    png_path, fragment = result
    assert isinstance(png_path, Path)
    assert "overlay=" in fragment


@pytest.mark.unit
def test_mini_map_build_returns_none_when_fetch_raises(tmp_path: Path) -> None:
    """build() returns None when urlopen raises any exception."""
    clip = _make_clip()
    config = Config()

    _patch_urlopen = "travel_video.overlays.mini_map.urllib.request.urlopen"
    with (
        patch("travel_video.overlays.mini_map.should_show") as mock_show,
        patch("travel_video.overlays.mini_map.cache") as mock_cache,
        patch(_patch_urlopen, side_effect=OSError("network error")),
    ):
        mock_show.return_value = True
        fake_png = tmp_path / "map.png"
        mock_cache.map_path.return_value = fake_png
        mock_cache.cache_key.return_value = "abc123"

        result = mini_map_build(clip, config)

    assert result is None
