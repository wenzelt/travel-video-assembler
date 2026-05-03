"""Tests for travel_video.ffmpeg.commands — written FIRST (TDD Red phase).

All subprocess calls are mocked — no real FFmpeg invocation ever occurs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from travel_video.ffmpeg.commands import (
    FFmpegError,
    concat_with_xfade,
    normalize_clip,
    probe_duration,
    run,
)

# ---------------------------------------------------------------------------
# 1. run — successful exit (returncode=0) — no exception raised
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_success_no_exception() -> None:
    """run() with returncode=0 does not raise."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        result = run(["-version"])

    mock_sub.assert_called_once()
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# 2. run — non-zero exit — raises FFmpegError
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_nonzero_raises_ffmpeg_error() -> None:
    """run() with returncode != 0 raises FFmpegError with a descriptive message."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 1
    mock_result.stderr = b"some ffmpeg error"
    mock_result.args = ["ffmpeg", "-version"]

    with (
        patch("subprocess.run", return_value=mock_result),
        pytest.raises(FFmpegError, match="FFmpeg exited with code 1"),
    ):
        run(["-version"])


@pytest.mark.unit
def test_run_nonzero_error_is_runtime_error() -> None:
    """FFmpegError is a subclass of RuntimeError."""
    assert issubclass(FFmpegError, RuntimeError)


# ---------------------------------------------------------------------------
# 3. run — dry_run=True — subprocess NOT called, returns success
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_dry_run_does_not_call_subprocess() -> None:
    """run(dry_run=True) does NOT invoke subprocess.run."""
    with patch("subprocess.run") as mock_sub:
        result = run(["-i", "input.mp4", "output.mp4"], dry_run=True)

    mock_sub.assert_not_called()
    assert result.returncode == 0


@pytest.mark.unit
def test_run_dry_run_logs_command(caplog: pytest.LogCaptureFixture) -> None:
    """run(dry_run=True) logs the full ffmpeg command."""
    import logging

    with (
        caplog.at_level(logging.INFO, logger="travel_video.ffmpeg.commands"),
        patch("subprocess.run"),
    ):
        run(["-i", "input.mp4", "output.mp4"], dry_run=True)

    assert "ffmpeg" in caplog.text
    assert "input.mp4" in caplog.text
    assert "output.mp4" in caplog.text


@pytest.mark.unit
def test_run_dry_run_returns_completed_process() -> None:
    """run(dry_run=True) returns a CompletedProcess with returncode=0."""
    with patch("subprocess.run"):
        result = run(["-version"], dry_run=True)

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# 4. probe_duration — parses float from stdout correctly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_probe_duration_parses_float() -> None:
    """probe_duration returns the duration as a float from ffprobe stdout."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b"12.345\n"

    with patch("subprocess.run", return_value=mock_result):
        duration = probe_duration(Path("/some/video.mp4"))

    assert duration == pytest.approx(12.345)


@pytest.mark.unit
def test_probe_duration_strips_whitespace() -> None:
    """probe_duration handles whitespace around the float value."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b"  5.0  \n"

    with patch("subprocess.run", return_value=mock_result):
        duration = probe_duration(Path("/some/clip.mp4"))

    assert duration == pytest.approx(5.0)


@pytest.mark.unit
def test_probe_duration_calls_ffprobe_with_correct_args() -> None:
    """probe_duration invokes ffprobe with the expected argument list."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b"3.0"

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        probe_duration(Path("/videos/test.mp4"))

    called_args = mock_sub.call_args[0][0]
    assert called_args[0] == "ffprobe"
    assert "-show_entries" in called_args
    assert "stream=duration" in called_args
    assert "/videos/test.mp4" in called_args


# ---------------------------------------------------------------------------
# 5. probe_duration — raises FFmpegError on non-zero exit
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_probe_duration_raises_on_nonzero_exit() -> None:
    """probe_duration raises FFmpegError when ffprobe returns a non-zero exit code."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 1
    mock_result.stdout = b""
    mock_result.stderr = b"No such file or directory"

    with patch("subprocess.run", return_value=mock_result), pytest.raises(FFmpegError):
        probe_duration(Path("/nonexistent/file.mp4"))


# ---------------------------------------------------------------------------
# 6. probe_duration — raises FFmpegError if output is not a float
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_probe_duration_raises_on_non_float_output() -> None:
    """probe_duration raises FFmpegError when ffprobe stdout is not parseable as float."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b"invalid"

    with (
        patch("subprocess.run", return_value=mock_result),
        pytest.raises(FFmpegError, match="[Cc]ould not parse"),
    ):
        probe_duration(Path("/some/video.mp4"))


@pytest.mark.unit
def test_probe_duration_falls_back_to_format_duration_when_stream_is_na() -> None:
    """probe_duration falls back to format duration if stream duration is 'N/A'."""
    mock_stream_res = MagicMock(spec=subprocess.CompletedProcess)
    mock_stream_res.returncode = 0
    mock_stream_res.stdout = b"N/A\n"

    mock_format_res = MagicMock(spec=subprocess.CompletedProcess)
    mock_format_res.returncode = 0
    mock_format_res.stdout = b"12.5\n"

    with patch("subprocess.run", side_effect=[mock_stream_res, mock_format_res]) as mock_sub:
        duration = probe_duration(Path("/some/video.mp4"))

    assert duration == 12.5
    assert mock_sub.call_count == 2
    second_call_args = mock_sub.call_args_list[1][0][0]
    assert "-show_entries" in second_call_args
    assert "format=duration" in second_call_args


@pytest.mark.unit
def test_probe_duration_raises_when_format_fallback_also_unparseable() -> None:
    """probe_duration raises FFmpegError when both stream and format durations are unparseable."""
    mock_stream_res = MagicMock(spec=subprocess.CompletedProcess)
    mock_stream_res.returncode = 0
    mock_stream_res.stdout = b"N/A\n"

    mock_format_res = MagicMock(spec=subprocess.CompletedProcess)
    mock_format_res.returncode = 0
    mock_format_res.stdout = b"N/A\n"

    with (
        patch("subprocess.run", side_effect=[mock_stream_res, mock_format_res]),
        pytest.raises(FFmpegError, match="[Cc]ould not parse"),
    ):
        probe_duration(Path("/some/video.mp4"))


@pytest.mark.unit
def test_probe_duration_raises_on_empty_output() -> None:
    """probe_duration raises FFmpegError when ffprobe stdout is empty."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0
    mock_result.stdout = b""

    with patch("subprocess.run", return_value=mock_result), pytest.raises(FFmpegError):
        probe_duration(Path("/some/video.mp4"))


# ---------------------------------------------------------------------------
# 7. normalize_clip — builds correct ffmpeg args
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_clip_builds_correct_args() -> None:
    """normalize_clip assembles the expected ffmpeg argument list."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    input_path = Path("/input/clip.mp4")
    output_path = Path("/output/norm.mp4")
    video_filter = "[0:v]scale=1080:1920[v]"
    audio_filter = "highpass=f=120,afftdn,loudnorm,apad"
    encoder = "h264_videotoolbox"
    bitrate = "12M"

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=input_path,
            output_path=output_path,
            video_filter=video_filter,
            audio_filter=audio_filter,
            encoder=encoder,
            bitrate=bitrate,
        )

    called_args = mock_sub.call_args[0][0]
    assert called_args[0] == "ffmpeg"
    assert "-y" in called_args
    assert "-i" in called_args
    assert str(input_path) in called_args
    assert "-filter_complex" in called_args
    assert video_filter in called_args
    assert "-map" in called_args
    assert "[v]" in called_args
    assert "-af" in called_args
    assert audio_filter in called_args
    assert "-c:v" in called_args
    assert encoder in called_args
    assert "-b:v" in called_args
    assert bitrate in called_args
    assert "-c:a" in called_args
    assert "aac" in called_args
    assert str(output_path) == called_args[-1]


@pytest.mark.unit
def test_normalize_clip_dry_run_does_not_call_subprocess() -> None:
    """normalize_clip with dry_run=True does not invoke subprocess.run."""
    with patch("subprocess.run") as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            dry_run=True,
        )

    mock_sub.assert_not_called()


# ---------------------------------------------------------------------------
# 7b. normalize_clip — extra_input_paths prepended as additional -i args
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_clip_extra_inputs_added_as_i_args() -> None:
    """normalize_clip with extra_input_paths prepends them as -i args before -filter_complex."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    input_path = Path("/input/clip.mp4")
    output_path = Path("/output/norm.mp4")
    extra_png = Path("/cache/map.png")
    video_filter = "[0:v]scale=1080:1920[v]"
    audio_filter = "highpass=f=120,apad"

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=input_path,
            output_path=output_path,
            video_filter=video_filter,
            audio_filter=audio_filter,
            encoder="h264_videotoolbox",
            bitrate="12M",
            extra_input_paths=[extra_png],
        )

    called_args = mock_sub.call_args[0][0]
    # The extra PNG must appear as a -i argument
    assert "-i" in called_args
    assert str(extra_png) in called_args
    # It must appear before -filter_complex
    idx_extra_i = called_args.index(str(extra_png))
    idx_filter = called_args.index("-filter_complex")
    assert idx_extra_i < idx_filter


@pytest.mark.unit
def test_normalize_clip_no_extra_inputs_behaves_as_before() -> None:
    """normalize_clip with extra_input_paths=None behaves identically to the original."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    input_path = Path("/input/clip.mp4")
    output_path = Path("/output/norm.mp4")

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=input_path,
            output_path=output_path,
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    # Only the main input should appear (one -i + input_path pair after -y)
    i_indices = [idx for idx, a in enumerate(called_args) if a == "-i"]
    assert len(i_indices) == 1
    assert called_args[i_indices[0] + 1] == str(input_path)


# ---------------------------------------------------------------------------
# 8. concat_with_xfade — 1 input — no xfade filter
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_concat_with_xfade_single_input_no_xfade() -> None:
    """concat_with_xfade with 1 input does not include xfade in the command."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4")]
    output = Path("/out/final.mp4")

    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=output,
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "xfade" not in " ".join(str(a) for a in called_args)
    assert "acrossfade" not in " ".join(str(a) for a in called_args)
    assert str(inputs[0]) in called_args
    assert str(output) == called_args[-1]


# ---------------------------------------------------------------------------
# 9. concat_with_xfade — 2 inputs — xfade filter present with correct offset
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_concat_with_xfade_two_inputs_xfade_present() -> None:
    """concat_with_xfade with 2 inputs includes xfade and acrossfade filters."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]
    output = Path("/out/final.mp4")

    # First clip duration is 5.0 s; xfade at offset = 5.0 - 0.5 = 4.5 s
    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=output,
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    full_cmd = " ".join(str(a) for a in called_args)
    assert "xfade" in full_cmd
    assert "acrossfade" in full_cmd
    assert "atrim" in full_cmd


@pytest.mark.unit
def test_concat_with_xfade_two_inputs_correct_offset() -> None:
    """concat_with_xfade with 2 inputs computes offset = duration[0] - xfade_seconds."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]
    output = Path("/out/final.mp4")

    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=output,
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    full_cmd = " ".join(str(a) for a in called_args)
    # offset = 5.0 - 0.5 = 4.5
    assert "offset=4.5" in full_cmd


@pytest.mark.unit
def test_concat_with_xfade_two_inputs_uses_both_input_files() -> None:
    """concat_with_xfade passes both input paths to ffmpeg."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]
    output = Path("/out/final.mp4")

    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=output,
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "/clips/a.mp4" in called_args
    assert "/clips/b.mp4" in called_args


@pytest.mark.unit
def test_concat_with_xfade_two_inputs_dry_run_does_not_call_subprocess() -> None:
    """concat_with_xfade with dry_run=True does not invoke subprocess.run."""
    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]

    with (
        patch("subprocess.run") as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=Path("/out/final.mp4"),
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
            dry_run=True,
        )

    mock_sub.assert_not_called()


@pytest.mark.unit
def test_concat_with_xfade_probes_all_inputs_for_alignment() -> None:
    """concat_with_xfade probes each input to compute xfade offsets and trim audio."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]

    probe_calls: list[Path] = []

    def fake_probe(path: Path) -> float:
        probe_calls.append(path)
        return 5.0

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("travel_video.ffmpeg.commands.probe_duration", side_effect=fake_probe),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=Path("/out/final.mp4"),
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    # BOTH clips must be probed now
    assert len(probe_calls) == 2


# ---------------------------------------------------------------------------
# M1 Mac — hardware acceleration in normalize_clip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_clip_uses_videotoolbox_hwaccel() -> None:
    """-hwaccel videotoolbox must appear in normalize_clip args for M1 hardware decode."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "-hwaccel" in called_args
    idx = called_args.index("-hwaccel")
    assert called_args[idx + 1] == "videotoolbox"


@pytest.mark.unit
def test_normalize_clip_hwaccel_precedes_input() -> None:
    """-hwaccel videotoolbox must appear before the main -i flag."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    idx_hwaccel = called_args.index("-hwaccel")
    idx_i = called_args.index("-i")
    assert idx_hwaccel < idx_i


@pytest.mark.unit
def test_normalize_clip_uses_noautorotate() -> None:
    """-noautorotate must be present so rotation is handled by the filter graph, not FFmpeg."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]transpose=1,scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "-noautorotate" in called_args


# ---------------------------------------------------------------------------
# M1 Mac — hardware acceleration in concat_with_xfade
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_concat_with_xfade_single_input_uses_videotoolbox() -> None:
    """Single-input concat_with_xfade must use -hwaccel videotoolbox for the input."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=[Path("/clips/a.mp4")],
            output=Path("/out/final.mp4"),
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "-hwaccel" in called_args
    idx = called_args.index("-hwaccel")
    assert called_args[idx + 1] == "videotoolbox"


@pytest.mark.unit
def test_concat_with_xfade_two_inputs_videotoolbox_per_input() -> None:
    """concat_with_xfade must put -hwaccel videotoolbox immediately before each -i."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    inputs = [Path("/clips/a.mp4"), Path("/clips/b.mp4")]

    with (
        patch("subprocess.run", return_value=mock_result) as mock_sub,
        patch("travel_video.ffmpeg.commands.probe_duration", return_value=5.0),
    ):
        concat_with_xfade(
            inputs=inputs,
            output=Path("/out/final.mp4"),
            xfade_seconds=0.5,
            encoder="h264_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    input_paths = {str(p) for p in inputs}
    # Each -i must be immediately preceded by -hwaccel videotoolbox
    i_indices = [
        idx
        for idx, a in enumerate(called_args)
        if a == "-i" and called_args[idx + 1] in input_paths
    ]
    assert len(i_indices) == 2, "expected two -i flags for two inputs"
    for idx_i in i_indices:
        assert called_args[idx_i - 2] == "-hwaccel"
        assert called_args[idx_i - 1] == "videotoolbox"


# ---------------------------------------------------------------------------
# M1 Mac — nv12 pixel format in filtergraph
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_nv12_format_in_all_modes() -> None:
    """All vertical_normalize modes must output format=nv12 for VideoToolbox compatibility."""
    from travel_video.ffmpeg.filters import vertical_normalize

    for mode in ("blur", "crop", "bars"):
        result = vertical_normalize(width=1920, height=1080, rotation=0, mode=mode)  # type: ignore[arg-type]
        assert "format=nv12" in result, f"format=nv12 missing for mode={mode!r}"


@pytest.mark.unit
def test_vertical_normalize_nv12_for_vertical_clip() -> None:
    """An already-vertical clip must still emit format=nv12."""
    from travel_video.ffmpeg.filters import vertical_normalize

    result = vertical_normalize(width=1080, height=1920, rotation=0, mode="blur")
    assert "format=nv12" in result


# ---------------------------------------------------------------------------
# M1 Mac — silent audio injection for clips without audio
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_clip_no_audio_injects_anullsrc() -> None:
    """normalize_clip with has_audio=False must inject anullsrc as a silent audio source."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/silent.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            has_audio=False,
        )

    called_args = mock_sub.call_args[0][0]
    full_cmd = " ".join(called_args)
    assert "anullsrc" in full_cmd
    assert "lavfi" in full_cmd


@pytest.mark.unit
def test_normalize_clip_no_audio_maps_injected_stream() -> None:
    """With has_audio=False and no extras, audio maps from stream index 1 (the anullsrc)."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/silent.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            has_audio=False,
        )

    called_args = mock_sub.call_args[0][0]
    # The -map for audio must reference stream 1:a:0 (input 0 is the clip, input 1 is anullsrc)
    assert "1:a:0" in called_args


@pytest.mark.unit
def test_normalize_clip_no_audio_with_one_extra_maps_correct_index() -> None:
    """With has_audio=False and 1 extra input, audio must map from stream index 2."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/silent.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            extra_input_paths=[Path("/cache/label.png")],
            has_audio=False,
        )

    called_args = mock_sub.call_args[0][0]
    # input 0=clip, input 1=extra PNG, input 2=anullsrc
    assert "2:a:0" in called_args


@pytest.mark.unit
def test_normalize_clip_has_audio_maps_optional_stream() -> None:
    """With has_audio=True (default), audio must use 0:a:0? (optional — clip may lack audio)."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            has_audio=True,
        )

    called_args = mock_sub.call_args[0][0]
    assert "0:a:0?" in called_args


@pytest.mark.unit
def test_normalize_clip_has_audio_does_not_inject_anullsrc() -> None:
    """With has_audio=True, no anullsrc must be injected."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="h264_videotoolbox",
            bitrate="12M",
            has_audio=True,
        )

    called_args = mock_sub.call_args[0][0]
    assert "anullsrc" not in " ".join(called_args)


# ---------------------------------------------------------------------------
# M1 Mac — hevc_videotoolbox encoder support
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normalize_clip_accepts_hevc_videotoolbox_encoder() -> None:
    """normalize_clip must accept hevc_videotoolbox as the encoder (M1 HEVC encode)."""
    mock_result = MagicMock(spec=subprocess.CompletedProcess)
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_sub:
        normalize_clip(
            input_path=Path("/input/clip.mp4"),
            output_path=Path("/output/norm.mp4"),
            video_filter="[0:v]scale=1080:1920[v]",
            audio_filter="highpass=f=120,apad",
            encoder="hevc_videotoolbox",
            bitrate="12M",
        )

    called_args = mock_sub.call_args[0][0]
    assert "hevc_videotoolbox" in called_args
