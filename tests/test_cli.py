"""Tests for travel_video.cli plan and inspect commands.

Written first (TDD Red phase) — all tests should FAIL until the implementation
is wired up.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from typer.testing import CliRunner

from travel_video.cli import app
from travel_video.models import Clip, DaySeparator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

runner = CliRunner()


def _make_clip(path: Path, day: int = 1) -> Clip:
    return Clip(
        path=path,
        duration_s=90.0,
        creation_time=datetime(2024, 7, day, 12, 0, 0),
        gps_lat=48.8584,
        gps_lon=2.2945,
        rotation=0,
        width=1920,
        height=1080,
    )


def _make_clip_no_gps(path: Path, day: int = 1) -> Clip:
    return Clip(
        path=path,
        duration_s=45.5,
        creation_time=datetime(2024, 7, day, 14, 0, 0),
        gps_lat=None,
        gps_lon=None,
        rotation=0,
        width=1280,
        height=720,
    )


# ---------------------------------------------------------------------------
# 1. Help output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_help_exits_zero() -> None:
    """plan --help exits 0."""
    result = runner.invoke(app, ["plan", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_plan_help_shows_input_option() -> None:
    """plan --help mentions --input."""
    result = runner.invoke(app, ["plan", "--help"])
    assert "--input" in result.output


@pytest.mark.unit
def test_plan_help_shows_config_option() -> None:
    """plan --help mentions --config."""
    result = runner.invoke(app, ["plan", "--help"])
    assert "--config" in result.output


@pytest.mark.unit
def test_inspect_help_exits_zero() -> None:
    """inspect --help exits 0."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_inspect_help_shows_file_argument() -> None:
    """inspect --help mentions FILE."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert "FILE" in result.output or "file" in result.output.lower()


# ---------------------------------------------------------------------------
# 2. Validation — plan command
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_missing_input_dir_exits_nonzero(tmp_path: Path) -> None:
    """plan --input nonexistent exits with a non-zero code."""
    missing = tmp_path / "does_not_exist"
    result = runner.invoke(
        app, ["plan", "--input", str(missing), "--config", str(tmp_path / "c.yaml")]
    )
    assert result.exit_code != 0


@pytest.mark.unit
def test_plan_input_is_file_not_dir_exits_nonzero(tmp_path: Path) -> None:
    """plan --input pointing to a file (not dir) exits with a non-zero code."""
    a_file = tmp_path / "not_a_dir.mp4"
    a_file.touch()
    cfg = tmp_path / "config.yaml"
    cfg.write_text("output:\n  container: mkv\n")
    result = runner.invoke(app, ["plan", "--input", str(a_file), "--config", str(cfg)])
    assert result.exit_code != 0


@pytest.mark.unit
def test_plan_missing_config_exits_nonzero(tmp_path: Path) -> None:
    """plan with --input valid dir but --config pointing to missing file exits non-zero."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    missing_cfg = tmp_path / "no_such_config.yaml"
    result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(missing_cfg)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 3. Validation — inspect command
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_inspect_missing_file_exits_nonzero(tmp_path: Path) -> None:
    """inspect with non-existent file exits with a non-zero code."""
    missing = tmp_path / "ghost.mp4"
    result = runner.invoke(app, ["inspect", str(missing)])
    assert result.exit_code != 0


@pytest.mark.unit
def test_inspect_directory_instead_of_file_exits_nonzero(tmp_path: Path) -> None:
    """inspect with a directory path (not a file) exits with a non-zero code."""
    result = runner.invoke(app, ["inspect", str(tmp_path)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 4. plan command — happy path with mocks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_plan_renders_table_with_clips(tmp_path: Path) -> None:
    """plan produces a table showing clip info when mocks return a valid timeline."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    clip_path = input_dir / "clip1.mp4"
    clip = _make_clip(clip_path, day=1)

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]) as mock_scan,
        patch("travel_video.cli.metadata.extract", return_value=clip) as mock_extract,
        patch("travel_video.cli.planner.build_timeline", return_value=[clip]) as mock_timeline,
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    mock_scan.assert_called_once_with(input_dir)
    mock_extract.assert_called_once_with(clip_path)
    mock_timeline.assert_called_once()
    # Table columns should appear
    assert "clip" in result.output.lower() or "#" in result.output


@pytest.mark.unit
def test_plan_renders_day_separator_row(tmp_path: Path) -> None:
    """plan renders DaySeparator as a 'day break' row."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    from datetime import date

    day_sep = DaySeparator(date=date(2024, 7, 2))
    clip_path = input_dir / "clip2.mp4"
    clip = _make_clip(clip_path, day=2)

    timeline = [day_sep, clip]

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=timeline),
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "day break" in result.output


@pytest.mark.unit
def test_plan_shows_summary_line(tmp_path: Path) -> None:
    """plan prints a summary with total clips, days, and duration."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    clip_path = input_dir / "clip1.mp4"
    clip = _make_clip(clip_path, day=1)

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=[clip]),
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "Total clips" in result.output
    assert "Total days" in result.output
    assert "Total duration" in result.output


@pytest.mark.unit
def test_plan_formats_duration_as_mm_ss(tmp_path: Path) -> None:
    """plan formats duration_s as MM:SS in the table."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    clip_path = input_dir / "clip1.mp4"
    # 90 seconds = 01:30
    clip = _make_clip(clip_path, day=1)  # duration_s=90.0

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=[clip]),
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "01:30" in result.output


@pytest.mark.unit
def test_plan_shows_gps_dash_when_absent(tmp_path: Path) -> None:
    """plan shows — for GPS when clip has no GPS data."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    clip_path = input_dir / "clip1.mp4"
    clip = _make_clip_no_gps(clip_path, day=1)

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=[clip]),
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "—" in result.output  # — (em dash)


@pytest.mark.unit
def test_plan_empty_directory_shows_zero_clips(tmp_path: Path) -> None:
    """plan with no video files prints a table with no clip rows and zero total."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    with (
        patch("travel_video.cli.scanner.scan", return_value=[]),
        patch("travel_video.cli.planner.build_timeline", return_value=[]),
        patch("travel_video.cli.Config.load") as mock_cfg,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(app, ["plan", "--input", str(input_dir), "--config", str(cfg_file)])

    assert result.exit_code == 0, result.output
    assert "0" in result.output


# ---------------------------------------------------------------------------
# 5. inspect command — happy path with mocks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_inspect_shows_clip_fields(tmp_path: Path) -> None:
    """inspect prints a Panel with Clip fields."""
    video_file = tmp_path / "clip.mp4"
    video_file.touch()

    clip = _make_clip(video_file, day=1)

    exiftool_json = json.dumps([{"SourceFile": str(video_file), "Duration": 90}])

    with (
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=exiftool_json, stderr="")
        result = runner.invoke(app, ["inspect", str(video_file)])

    assert result.exit_code == 0, result.output
    # Field names should appear in the panel
    assert "duration" in result.output.lower() or "Duration" in result.output
    assert "1920" in result.output or "width" in result.output.lower()


@pytest.mark.unit
def test_inspect_shows_raw_exiftool_panel(tmp_path: Path) -> None:
    """inspect prints a second panel titled 'Raw ExifTool output'."""
    video_file = tmp_path / "clip.mp4"
    video_file.touch()

    clip = _make_clip(video_file, day=1)
    exiftool_json = json.dumps([{"SourceFile": str(video_file), "Duration": 90}])

    with (
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=exiftool_json, stderr="")
        result = runner.invoke(app, ["inspect", str(video_file)])

    assert result.exit_code == 0, result.output
    assert "exiftool" in result.output.lower()


@pytest.mark.unit
def test_inspect_shows_gps_coordinates(tmp_path: Path) -> None:
    """inspect shows GPS lat/lon when present."""
    video_file = tmp_path / "clip.mp4"
    video_file.touch()

    clip = _make_clip(video_file, day=1)  # has gps_lat=48.8584, gps_lon=2.2945
    exiftool_json = json.dumps([{"SourceFile": str(video_file)}])

    with (
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=exiftool_json, stderr="")
        result = runner.invoke(app, ["inspect", str(video_file)])

    assert result.exit_code == 0, result.output
    assert "48" in result.output  # lat present


@pytest.mark.unit
def test_inspect_exiftool_failure_shows_error(tmp_path: Path) -> None:
    """inspect gracefully handles exiftool non-zero exit (shows error, still exits 0 for panel)."""
    video_file = tmp_path / "clip.mp4"
    video_file.touch()

    clip = _make_clip(video_file, day=1)

    with (
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="exiftool not found")
        result = runner.invoke(app, ["inspect", str(video_file)])

    # Should still show clip metadata panel, even if exiftool raw call fails
    assert (
        "duration" in result.output.lower()
        or "width" in result.output.lower()
        or result.exit_code == 0
    )


# ---------------------------------------------------------------------------
# 6. render command — help and validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_help_exits_zero() -> None:
    """render --help exits 0."""
    result = runner.invoke(app, ["render", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_render_missing_input_exits_nonzero(tmp_path: Path) -> None:
    """render with a non-existent --input dir exits non-zero."""
    missing = tmp_path / "does_not_exist"
    cfg = tmp_path / "config.yaml"
    cfg.write_text("output:\n  container: mkv\n")
    result = runner.invoke(
        app,
        [
            "render",
            "--input",
            str(missing),
            "--output",
            str(tmp_path / "out.mkv"),
            "--config",
            str(cfg),
        ],
    )
    assert result.exit_code != 0


@pytest.mark.unit
def test_render_missing_config_exits_nonzero(tmp_path: Path) -> None:
    """render with existing --input dir but missing --config file exits non-zero."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    missing_cfg = tmp_path / "no_such_config.yaml"
    result = runner.invoke(
        app,
        [
            "render",
            "--input",
            str(input_dir),
            "--output",
            str(tmp_path / "out.mkv"),
            "--config",
            str(missing_cfg),
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 7. render command — no clips early return
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_no_clips_returns_early(tmp_path: Path) -> None:
    """render prints a warning and returns early (without calling renderer) when no clips found."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")

    with (
        patch("travel_video.cli.scanner.scan", return_value=[]),
        patch("travel_video.cli.Config.load") as mock_cfg,
        patch("travel_video.cli.renderer.render") as mock_renderer,
    ):
        mock_cfg.return_value = MagicMock()
        result = runner.invoke(
            app,
            [
                "render",
                "--input",
                str(input_dir),
                "--output",
                str(tmp_path / "out.mkv"),
                "--config",
                str(cfg_file),
            ],
        )

    assert result.exit_code == 0, result.output
    mock_renderer.assert_not_called()


# ---------------------------------------------------------------------------
# 8. render command — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_calls_renderer(tmp_path: Path) -> None:
    """render calls renderer.render with the correct output path and dry_run=False."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")
    output_path = tmp_path / "out" / "travel.mkv"

    clip_path = input_dir / "clip1.mp4"
    clip = _make_clip(clip_path, day=1)
    timeline = [clip]
    cfg_obj = MagicMock()

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=timeline),
        patch("travel_video.cli.Config.load", return_value=cfg_obj),
        patch("travel_video.cli.renderer.render") as mock_renderer,
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "--input",
                str(input_dir),
                "--output",
                str(output_path),
                "--config",
                str(cfg_file),
            ],
        )

        assert result.exit_code == 0, result.output
        mock_renderer.assert_called_once_with(timeline, cfg_obj, output_path, dry_run=False, progress_callback=ANY)


@pytest.mark.unit
def test_render_dry_run_flag(tmp_path: Path) -> None:
    """render calls renderer.render with dry_run=True when --dry-run is passed."""
    input_dir = tmp_path / "clips"
    input_dir.mkdir()
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("output:\n  container: mkv\n")
    output_path = tmp_path / "out.mkv"

    clip_path = input_dir / "clip1.mp4"
    clip = _make_clip(clip_path, day=1)
    timeline = [clip]
    cfg_obj = MagicMock()

    with (
        patch("travel_video.cli.scanner.scan", return_value=[clip_path]),
        patch("travel_video.cli.metadata.extract", return_value=clip),
        patch("travel_video.cli.planner.build_timeline", return_value=timeline),
        patch("travel_video.cli.Config.load", return_value=cfg_obj),
        patch("travel_video.cli.renderer.render") as mock_renderer,
    ):
        result = runner.invoke(
            app,
            [
                "render",
                "--input",
                str(input_dir),
                "--output",
                str(output_path),
                "--config",
                str(cfg_file),
                "--dry-run",
            ],
        )

    assert result.exit_code == 0, result.output
    mock_renderer.assert_called_once_with(timeline, cfg_obj, output_path, dry_run=True, progress_callback=ANY)
