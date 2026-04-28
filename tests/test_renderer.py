"""Tests for travel_video.renderer — written FIRST (TDD Red phase).

All FFmpeg subprocess calls are mocked.  cache_key and normalized_path are
allowed to run for real (they only touch the filesystem via tmp_path).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from travel_video.config import Config
from travel_video.models import Clip, DaySeparator
from travel_video.renderer import render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_clip(
    path: Path,
    width: int = 1080,
    height: int = 1920,
    rotation: int = 0,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
) -> Clip:
    """Create a minimal Clip with the given path and dimensions."""
    return Clip(
        path=path,
        duration_s=5.0,
        creation_time=datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC),
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        rotation=rotation,
        width=width,
        height=height,
    )


def _make_day_sep(d: date = date(2024, 7, 2)) -> DaySeparator:
    return DaySeparator(date=d)


def _default_config() -> Config:
    return Config()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point TRAVEL_VIDEO_CACHE_DIR to a fresh temp directory for each test."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(cache))
    return cache


# ---------------------------------------------------------------------------
# 1. Single clip: normalize_clip called, concat_with_xfade called with
#    the normalized path.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_single_clip_normalize_and_concat(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """render() normalises the clip and concat is called with the normalized path."""
    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()
    clip = _make_clip(clip_file)

    output = tmp_path / "out.mkv"
    config = _default_config()

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run") as mock_run,
    ):

        render([clip], config, output)

    mock_norm.assert_called_once()
    norm_call_kwargs = mock_norm.call_args

    # Second positional arg is output_path (the cached normalized path)
    normalized = norm_call_kwargs[0][1]
    assert isinstance(normalized, Path)
    assert normalized.suffix == ".mkv"

    mock_concat.assert_called_once()
    concat_segments = mock_concat.call_args[0][0]
    assert concat_segments == [normalized]

    # day-separator ffmpeg run should NOT be called (no DaySeparator in timeline)
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Two clips, same day: both normalized, concat called with both paths.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_two_clips_both_normalized(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """render() normalises each clip independently and passes both to concat."""
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.touch()
    clip_b.touch()

    timeline = [_make_clip(clip_a), _make_clip(clip_b)]
    output = tmp_path / "out.mkv"
    config = _default_config()

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run"),
    ):

        render(timeline, config, output)

    assert mock_norm.call_count == 2

    # Gather the two normalized output paths from calls
    norm_out_a = mock_norm.call_args_list[0][0][1]
    norm_out_b = mock_norm.call_args_list[1][0][1]

    concat_segments = mock_concat.call_args[0][0]
    assert concat_segments == [norm_out_a, norm_out_b]


# ---------------------------------------------------------------------------
# 3. One clip + DaySeparator + one clip: separator path in segment list.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_clip_daysep_clip_separator_in_segments(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """render() includes the separator clip between the two clip normalized paths."""
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.touch()
    clip_b.touch()

    timeline = [_make_clip(clip_a), _make_day_sep(), _make_clip(clip_b)]
    output = tmp_path / "out.mkv"
    config = _default_config()

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run") as mock_run,
    ):

        render(timeline, config, output)

    assert mock_norm.call_count == 2
    assert mock_run.call_count == 1  # one day-separator generated

    # Separator path must sit between the two clip paths in the segment list
    concat_segments = mock_concat.call_args[0][0]
    assert len(concat_segments) == 3

    norm_out_a = mock_norm.call_args_list[0][0][1]
    norm_out_b = mock_norm.call_args_list[1][0][1]
    sep_path = concat_segments[1]

    assert concat_segments[0] == norm_out_a
    assert concat_segments[2] == norm_out_b
    # Middle entry is different from both clip paths
    assert sep_path != norm_out_a
    assert sep_path != norm_out_b
    assert isinstance(sep_path, Path)


# ---------------------------------------------------------------------------
# 4. Cache hit: normalize_clip NOT called for a clip whose output already
#    exists.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_hit_skips_normalization(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """normalize_clip is NOT called when the normalized file already exists."""
    import hashlib

    from travel_video.cache import cache_key, normalized_path

    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()

    config = _default_config()

    # Reproduce the overlay_sig the renderer computes for the default config.
    overlay_sig = hashlib.sha1(
        (
            f"{config.overlays.location_label.enabled}"
            f":{config.overlays.mini_map.enabled}"
            f":{config.overlays.mini_map.probability}"
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:8]

    # Pre-populate the cache with a fake normalized file using the full key.
    base_key = cache_key(clip_file)
    full_key = f"{base_key}_{overlay_sig}"
    expected_norm = normalized_path(full_key)
    expected_norm.touch()

    clip = _make_clip(clip_file)
    output = tmp_path / "out.mkv"

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade"),
        patch("travel_video.renderer.commands.run"),
    ):

        render([clip], config, output)

    mock_norm.assert_not_called()


# ---------------------------------------------------------------------------
# 5. dry_run=True: all commands called with dry_run=True
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dry_run_propagated_to_all_commands(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """All command calls receive dry_run=True when render is called with dry_run=True."""
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.touch()
    clip_b.touch()

    timeline = [_make_clip(clip_a), _make_day_sep(), _make_clip(clip_b)]
    output = tmp_path / "out.mkv"
    config = _default_config()

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run") as mock_run,
    ):

        render(timeline, config, output, dry_run=True)

    # Every normalize_clip call must have dry_run=True
    for c in mock_norm.call_args_list:
        assert c.kwargs.get("dry_run") is True, f"normalize_clip call missing dry_run=True: {c}"

    # concat_with_xfade must have dry_run=True
    concat_call = mock_concat.call_args
    assert concat_call.kwargs.get("dry_run") is True

    # The day-separator run() call must also carry dry_run=True
    run_call = mock_run.call_args
    assert run_call.kwargs.get("dry_run") is True


# ---------------------------------------------------------------------------
# 6. Day-separator cache hit: commands.run NOT called a second time
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_day_separator_cache_hit_skips_generation(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """Day-separator generation is skipped when the separator file already exists."""
    from travel_video.cache import normalized_path

    config = _default_config()
    sep_key = (
        f"day_sep_{config.transitions.day_break_seconds}s_"
        f"{config.output.width}x{config.output.height}"
    )
    sep_path = normalized_path(sep_key)
    sep_path.touch()

    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.touch()
    clip_b.touch()

    timeline = [_make_clip(clip_a), _make_day_sep(), _make_clip(clip_b)]
    output = tmp_path / "out.mkv"

    with (
        patch("travel_video.renderer.commands.normalize_clip"),
        patch("travel_video.renderer.commands.concat_with_xfade"),
        patch("travel_video.renderer.commands.run") as mock_run,
    ):

        render(timeline, config, output)

    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# 7. concat_with_xfade receives correct keyword arguments
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_concat_receives_correct_config_params(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """concat_with_xfade is called with xfade_s, encoder and bitrate from config."""
    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()

    config = _default_config()
    output = tmp_path / "out.mkv"

    with (
        patch("travel_video.renderer.commands.normalize_clip"),
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run"),
    ):

        render([_make_clip(clip_file)], config, output)

    concat_call = mock_concat.call_args
    assert concat_call[0][1] == output
    assert concat_call[0][2] == config.transitions.clip_crossfade_seconds
    assert concat_call[0][3] == config.video.encoder
    assert concat_call[0][4] == config.video.bitrate


# ---------------------------------------------------------------------------
# 8. Empty timeline: concat_with_xfade is called with an empty segment list
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_timeline(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """render() with an empty timeline calls concat with an empty list."""
    output = tmp_path / "out.mkv"
    config = _default_config()

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade") as mock_concat,
        patch("travel_video.renderer.commands.run"),
    ):

        render([], config, output)

    mock_norm.assert_not_called()
    concat_segments = mock_concat.call_args[0][0]
    assert concat_segments == []


# ---------------------------------------------------------------------------
# 9. location_label overlay applied when enabled
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_location_label_applied_when_enabled(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """When location_label is enabled, normalize_clip receives the drawtext fragment."""
    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()
    clip = _make_clip(clip_file, gps_lat=48.8566, gps_lon=2.3522)

    config = _default_config()

    drawtext_fragment = "drawtext=text='Paris, France, FR':x=w-tw-48:y=h-th-48"

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade"),
        patch("travel_video.renderer.commands.run"),
        patch(
            "travel_video.renderer.location_label.build",
            return_value=drawtext_fragment,
        ) as mock_label,
    ):
        render([clip], config, output_path=tmp_path / "out.mkv")

    mock_label.assert_called_once_with(clip)
    assert mock_norm.call_count == 1
    # video_filter arg (positional index 2) must contain the drawtext fragment
    video_filter_used = mock_norm.call_args[0][2]
    assert drawtext_fragment in video_filter_used


# ---------------------------------------------------------------------------
# 10. location_label NOT called when overlay is disabled
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_location_label_skipped_when_disabled(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """When location_label is disabled, location_label.build is never called."""
    from travel_video.config import OverlayItemConfig, OverlaysConfig

    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()
    clip = _make_clip(clip_file, gps_lat=48.8566, gps_lon=2.3522)

    config = _default_config()
    config = config.model_copy(
        update={
            "overlays": OverlaysConfig(
                location_label=OverlayItemConfig(enabled=False),
                mini_map=OverlayItemConfig(enabled=False),
            )
        }
    )

    with (
        patch("travel_video.renderer.commands.normalize_clip"),
        patch("travel_video.renderer.commands.concat_with_xfade"),
        patch("travel_video.renderer.commands.run"),
        patch("travel_video.renderer.location_label.build") as mock_label,
    ):
        render([clip], config, output_path=tmp_path / "out.mkv")

    mock_label.assert_not_called()


# ---------------------------------------------------------------------------
# 11. mini_map applied when location_label returns None
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mini_map_applied_when_label_none(
    tmp_path: Path,
    cache_dir: Path,
) -> None:
    """When location_label returns None, mini_map.build result is passed to normalize_clip."""
    from travel_video.config import OverlayItemConfig, OverlaysConfig

    clip_file = tmp_path / "clip.mp4"
    clip_file.touch()
    clip = _make_clip(clip_file, gps_lat=48.8566, gps_lon=2.3522)

    config = _default_config()
    config = config.model_copy(
        update={
            "overlays": OverlaysConfig(
                location_label=OverlayItemConfig(enabled=True),
                mini_map=OverlayItemConfig(enabled=True),
            )
        }
    )

    map_png = tmp_path / "map.png"
    map_png.touch()
    overlay_fragment = "overlay=W-w-48:48"

    with (
        patch("travel_video.renderer.commands.normalize_clip") as mock_norm,
        patch("travel_video.renderer.commands.concat_with_xfade"),
        patch("travel_video.renderer.commands.run"),
        patch("travel_video.renderer.location_label.build", return_value=None),
        patch(
            "travel_video.renderer.mini_map.build",
            return_value=(map_png, overlay_fragment),
        ) as mock_map,
    ):
        render([clip], config, output_path=tmp_path / "out.mkv")

    mock_map.assert_called_once_with(clip, config)
    assert mock_norm.call_count == 1
    # extra_input_paths kwarg (passed to commands.normalize_clip) must contain the map png
    norm_kwargs = mock_norm.call_args[1]
    extra_input_paths = norm_kwargs.get("extra_input_paths") or []
    assert map_png in extra_input_paths
