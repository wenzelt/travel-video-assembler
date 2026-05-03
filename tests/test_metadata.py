"""Tests for travel_video.metadata — written FIRST (TDD Red phase)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from travel_video.metadata import extract
from travel_video.models import Clip

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def _make_completed_process(fixture_name: str) -> MagicMock:
    """Return a mock CompletedProcess with stdout from the named fixture."""
    fixture_path = FIXTURES / fixture_name
    stdout = fixture_path.read_text(encoding="utf-8")
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.returncode = 0
    mock.stdout = stdout
    return mock


def _fake_stat(mtime: float) -> MagicMock:
    """Return a stat_result-like mock with st_mtime set."""
    stat = MagicMock()
    stat.st_mtime = mtime
    stat.st_mtime_ns = int(mtime * 1e9)
    return stat


# ---------------------------------------------------------------------------
# 1. Full extraction — all fields present, GPS as float, date as string
# ---------------------------------------------------------------------------


def test_extract_full_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All Clip fields populated correctly when ExifTool returns complete data."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_full.json")

    with (
        patch("subprocess.run", return_value=mock_proc) as mock_run,
        patch("travel_video.cache.cache_key", return_value="test-key-full"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    mock_run.assert_called_once()
    assert isinstance(clip, Clip)
    assert clip.path == video
    assert clip.duration_s == pytest.approx(83.0)
    assert clip.creation_time == datetime(2024, 1, 15, 14, 30, 0)
    assert clip.gps_lat == pytest.approx(48.8584)
    assert clip.gps_lon == pytest.approx(2.2945)
    assert clip.rotation == 0
    assert clip.width == 1920
    assert clip.height == 1080


# ---------------------------------------------------------------------------
# 2. Missing GPS → gps_lat and gps_lon are None
# ---------------------------------------------------------------------------


def test_extract_missing_gps_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clip.gps_lat and gps_lon are None when GPS fields absent in ExifTool output."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_no_gps.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-nogps"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.gps_lat is None
    assert clip.gps_lon is None


# ---------------------------------------------------------------------------
# 3. Missing CreateDate → falls back to st_mtime
# ---------------------------------------------------------------------------


def test_extract_missing_date_falls_back_to_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """creation_time is derived from st_mtime when no EXIF date is present."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    known_mtime = 1_700_000_000.0  # 2023-11-14 22:13:20 UTC

    expected_dt = datetime.fromtimestamp(known_mtime, tz=UTC)

    mock_proc = _make_completed_process("exif_no_date.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-nodate"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
        patch.object(Path, "stat", return_value=_fake_stat(known_mtime)),
    ):
        clip = extract(video)

    assert clip.creation_time == expected_dt


# ---------------------------------------------------------------------------
# 4. GPS as directional string "48.8584 N" → positive float
# ---------------------------------------------------------------------------


def test_extract_gps_directional_north_east(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPS strings with N/E suffixes are parsed as positive floats."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_gps_directional.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-gpsdir"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.gps_lat == pytest.approx(48.8584)
    assert clip.gps_lon == pytest.approx(2.2945)


# ---------------------------------------------------------------------------
# 5. GPS South "33.8688 S" → parsed as negative float
# ---------------------------------------------------------------------------


def test_extract_gps_south_is_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPS strings with S suffix produce negative latitude values."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_gps_south.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-gpssouth"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.gps_lat == pytest.approx(-33.8688)
    assert clip.gps_lon == pytest.approx(151.2093)


# ---------------------------------------------------------------------------
# 6. Duration as string "0:01:23" → 83.0 seconds
# ---------------------------------------------------------------------------


def test_extract_duration_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duration string '0:01:23' is converted to 83.0 float seconds."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_duration_string.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-durstr"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.duration_s == pytest.approx(83.0)


# ---------------------------------------------------------------------------
# 7. Cache hit → subprocess.run NOT called
# ---------------------------------------------------------------------------


def test_extract_cache_hit_skips_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When metadata_cache_get returns a hit, subprocess.run is never invoked."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    cached_data = {
        "path": str(video),
        "duration_s": 42.0,
        "creation_time": "2024-05-20T10:00:00",
        "gps_lat": 40.7128,
        "gps_lon": -74.0060,
        "rotation": 0,
        "width": 1920,
        "height": 1080,
    }

    with (
        patch("subprocess.run") as mock_run,
        patch("travel_video.cache.cache_key", return_value="cached-key"),
        patch("travel_video.cache.metadata_cache_get", return_value=cached_data),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    mock_run.assert_not_called()
    assert isinstance(clip, Clip)
    assert clip.duration_s == pytest.approx(42.0)
    assert clip.gps_lat == pytest.approx(40.7128)
    assert clip.gps_lon == pytest.approx(-74.0060)


# ---------------------------------------------------------------------------
# 8. Rotation fallback: Composite:Rotation used when Rotation missing
# ---------------------------------------------------------------------------


def test_extract_composite_rotation_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Composite:Rotation is used when Rotation key is absent."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_composite_rotation.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-comprot"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.rotation == 270


# ---------------------------------------------------------------------------
# 9. ExifTool non-zero exit code → RuntimeError with descriptive message
# ---------------------------------------------------------------------------


def test_extract_exiftool_nonzero_raises_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RuntimeError is raised when exiftool exits with a non-zero return code."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "exiftool: error processing file"

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-err"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        pytest.raises(RuntimeError, match="exiftool"),
    ):
        extract(video)


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_extract_rotation_defaults_to_zero_when_both_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rotation is 0 when neither Rotation nor Composite:Rotation is present."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 1.0,
        "ImageWidth": 640,
        "ImageHeight": 480,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-norot"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.rotation == 0


def test_extract_media_create_date_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MediaCreateDate is used when CreateDate is absent."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "MediaCreateDate": "2024:02:14 08:00:00",
        "Duration": 5.0,
        "ImageWidth": 1280,
        "ImageHeight": 720,
        "Rotation": 0,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-media"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.creation_time == datetime(2024, 2, 14, 8, 0, 0)


def test_extract_duration_value_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DurationValue field is used when Duration is absent."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:03:01 12:00:00",
        "DurationValue": 99.5,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "Rotation": 0,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-durval"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.duration_s == pytest.approx(99.5)


def test_extract_duration_with_fractional_seconds_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duration string '1:23:45.67' is converted correctly to float seconds."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:03:01 12:00:00",
        "Duration": "1:23:45.67",
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "Rotation": 0,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-fractime"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    # 1h * 3600 + 23m * 60 + 45.67s = 5025.67
    assert clip.duration_s == pytest.approx(5025.67)


def test_extract_gps_dms_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPS in DMS format '48 deg 51\\' 30.24\" N' is parsed correctly."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:04:01 10:00:00",
        "GPSLatitude": "48 deg 51' 30.24\" N",
        "GPSLongitude": "2 deg 17' 40.20\" E",
        "Duration": 10.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "Rotation": 0,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-dms"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    # 48 + 51/60 + 30.24/3600 = 48.858400
    assert clip.gps_lat == pytest.approx(48.8584, rel=1e-4)
    assert clip.gps_lon == pytest.approx(2.2945, rel=1e-4)


def test_extract_calls_cache_set_on_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """metadata_cache_set is called with a JSON-serialisable dict on a cache miss."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    mock_proc = _make_completed_process("exif_full.json")

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-setcheck"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set") as mock_set,
    ):
        extract(video)

    mock_set.assert_called_once()
    key_arg, data_arg = mock_set.call_args[0]
    assert key_arg == "test-key-setcheck"
    # Verify the stored data is JSON-serialisable
    serialised = json.dumps(data_arg)
    assert serialised  # non-empty


# ---------------------------------------------------------------------------
# Fix 6: DMS South/West test
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Bug: has_audio always False because _EXIFTOOL_FIELDS didn't request audio tags
# ---------------------------------------------------------------------------


def test_exiftool_command_requests_audio_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exiftool invocation must include -AudioChannels so audio detection works."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "AudioChannels": 2,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc) as mock_run,
        patch("travel_video.cache.cache_key", return_value="test-key-audio-cmd"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        extract(video)

    called_cmd = mock_run.call_args[0][0]
    assert "-AudioChannels" in called_cmd, (
        "ExifTool command must include -AudioChannels; without it has_audio is always False"
    )


def test_exiftool_command_requests_audio_sample_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exiftool invocation must include -AudioSampleRate as a fallback audio presence signal."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "AudioSampleRate": 48000,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc) as mock_run,
        patch("travel_video.cache.cache_key", return_value="test-key-audio-sr"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        extract(video)

    called_cmd = mock_run.call_args[0][0]
    assert "-AudioSampleRate" in called_cmd


def test_has_audio_true_when_exiftool_returns_audio_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """has_audio is True when ExifTool reports AudioChannels > 0."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "AudioChannels": 2,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-has-audio-ch"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.has_audio is True


def test_has_audio_true_when_exiftool_returns_audio_sample_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """has_audio is True when ExifTool reports AudioSampleRate (even without AudioChannels)."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "AudioSampleRate": 44100,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-has-audio-sr"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.has_audio is True


def test_has_audio_false_when_no_audio_tags_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """has_audio is False when ExifTool returns no audio-related tags (video-only clip)."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:01:01 00:00:00",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-no-audio"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.has_audio is False


def test_extract_gps_dms_south_west(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPS DMS string with S suffix parses to a negative float."""
    monkeypatch.setenv("TRAVEL_VIDEO_CACHE_DIR", str(tmp_path / "cache"))

    video = tmp_path / "clip.mp4"
    video.touch()

    exif_data = json.dumps([{
        "SourceFile": str(video),
        "CreateDate": "2024:06:01 09:00:00",
        "GPSLatitude": "33 deg 52' 0.00\" S",
        "GPSLongitude": "151 deg 12' 33.48\" W",
        "Duration": 5.0,
        "ImageWidth": 1920,
        "ImageHeight": 1080,
        "Rotation": 0,
    }])
    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = exif_data

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("travel_video.cache.cache_key", return_value="test-key-dms-sw"),
        patch("travel_video.cache.metadata_cache_get", return_value=None),
        patch("travel_video.cache.metadata_cache_set"),
    ):
        clip = extract(video)

    assert clip.gps_lat is not None
    assert clip.gps_lat < 0, "S hemisphere must produce negative latitude"
    assert clip.gps_lon is not None
    assert clip.gps_lon < 0, "W hemisphere must produce negative longitude"
