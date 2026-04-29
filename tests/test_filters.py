"""Tests for travel_video.ffmpeg.filters — updated for M1 optimizations.

All tests use exact string (snapshot) comparison to lock in the contract
for each filtergraph builder.
"""

from __future__ import annotations

import pytest

from travel_video.ffmpeg.filters import (
    audio_chain,
    black_screen,
    crossfade_audio,
    crossfade_video,
    vertical_normalize,
)

# ---------------------------------------------------------------------------
# 1. vertical_normalize — horizontal clip (1920×1080), mode=blur (default)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_horizontal_blur() -> None:
    """A 1920×1080 clip with mode='blur' produces the split/boxblur pattern."""
    result = vertical_normalize(width=1920, height=1080, rotation=0, mode="blur")
    expected = (
        "[0:v]fps=30,split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[bg2];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,format=nv12[v]"
    )
    assert result == expected


# ---------------------------------------------------------------------------
# 2. vertical_normalize — already-vertical clip (1080×1920), mode=blur
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_vertical_clip() -> None:
    """A 1080×1920 clip is already vertical — simple scale only."""
    result = vertical_normalize(width=1080, height=1920, rotation=0, mode="blur")
    assert result == "[0:v]fps=30,scale=1080:1920,format=nv12[v]"


# ---------------------------------------------------------------------------
# 3. vertical_normalize — mode=crop
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_crop_mode() -> None:
    """mode='crop' returns the scale+crop filter."""
    result = vertical_normalize(width=1920, height=1080, rotation=0, mode="crop")
    assert result == "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=nv12[v]"


# ---------------------------------------------------------------------------
# 4. vertical_normalize — mode=bars
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_bars_mode() -> None:
    """mode='bars' returns the scale+pad filter."""
    result = vertical_normalize(width=1920, height=1080, rotation=0, mode="bars")
    assert result == (
        "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=nv12[v]"
    )


# ---------------------------------------------------------------------------
# 5. vertical_normalize — rotation=90 (landscape clip becomes portrait)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_rotation_90_landscape_becomes_portrait() -> None:
    """A 1920×1080 clip rotated 90° has effective dims 1080×1920 (portrait) — simple scale."""
    result = vertical_normalize(width=1920, height=1080, rotation=90, mode="blur")
    assert result == "[0:v]transpose=1,fps=30,scale=1080:1920,format=nv12[v]"


# ---------------------------------------------------------------------------
# 5b. vertical_normalize — rotation=270
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_rotation_270() -> None:
    """A 1920×1080 clip rotated 270° is also portrait after rotation — simple scale."""
    result = vertical_normalize(width=1920, height=1080, rotation=270, mode="blur")
    assert result == "[0:v]transpose=2,fps=30,scale=1080:1920,format=nv12[v]"


# ---------------------------------------------------------------------------
# 5c. vertical_normalize — rotation=180 on a horizontal clip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_rotation_180_horizontal() -> None:
    """A 1920×1080 clip rotated 180° is still horizontal — blur pattern with transpose prefix."""
    result = vertical_normalize(width=1920, height=1080, rotation=180, mode="blur")
    expected = (
        "[0:v]transpose=1,transpose=1,fps=30,split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[bg2];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,format=nv12[v]"
    )
    assert result == expected


# ---------------------------------------------------------------------------
# 6. audio_chain — all options enabled (defaults)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audio_chain_all_enabled() -> None:
    """Default audio_chain includes highpass, resample, format, denoise, and loudnorm."""
    result = audio_chain(highpass_hz=120, denoise="afftdn", loudnorm=True)
    assert result == "highpass=f=120,aresample=48000,aformat=channel_layouts=stereo,afftdn,loudnorm"


# ---------------------------------------------------------------------------
# 7. audio_chain — loudnorm=False
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audio_chain_no_loudnorm() -> None:
    """With loudnorm=False, the loudnorm filter is omitted."""
    result = audio_chain(highpass_hz=120, denoise="afftdn", loudnorm=False)
    assert result == "highpass=f=120,aresample=48000,aformat=channel_layouts=stereo,afftdn"


# ---------------------------------------------------------------------------
# 8. audio_chain — denoise=None
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audio_chain_no_denoise() -> None:
    """With denoise=None, the denoise filter is omitted."""
    result = audio_chain(highpass_hz=120, denoise=None, loudnorm=True)
    assert result == "highpass=f=120,aresample=48000,aformat=channel_layouts=stereo,loudnorm"


# ---------------------------------------------------------------------------
# 8b. audio_chain — denoise="" (empty string)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audio_chain_empty_denoise() -> None:
    """With denoise='', the denoise filter is also omitted."""
    result = audio_chain(highpass_hz=120, denoise="", loudnorm=True)
    assert result == "highpass=f=120,aresample=48000,aformat=channel_layouts=stereo,loudnorm"


# ---------------------------------------------------------------------------
# 9. crossfade_video — exact output string
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_crossfade_video() -> None:
    """crossfade_video returns the correct xfade filtergraph string."""
    result = crossfade_video(
        duration_s=0.5,
        offset_s=4.5,
        in_label="v0",
        out_label="v1",
    )
    assert result == "[v0]xfade=transition=fade:duration=0.5:offset=4.5[v1]"


# ---------------------------------------------------------------------------
# 10. crossfade_audio — exact output string
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_crossfade_audio() -> None:
    """crossfade_audio returns the correct acrossfade filtergraph string."""
    result = crossfade_audio(
        duration_s=0.5,
        offset_s=4.5,
        in_label="a0",
        out_label="a1",
    )
    assert result == "[a0]acrossfade=d=0.5:c1=tri:c2=tri[a1]"


# ---------------------------------------------------------------------------
# 11. black_screen — default dimensions and duration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_black_screen_defaults() -> None:
    """black_screen with defaults returns the correct color+aevalsrc string."""
    result = black_screen()
    assert result == "color=c=black:s=1080x1920:d=3.0:r=30[v];aevalsrc=0:d=3.0[a]"


# ---------------------------------------------------------------------------
# 12. black_screen — custom duration and dimensions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_black_screen_custom() -> None:
    """black_screen with custom args reflects those values in the output."""
    result = black_screen(duration_s=5.0, width=720, height=1280)
    assert result == "color=c=black:s=720x1280:d=5.0:r=30[v];aevalsrc=0:d=5.0[a]"


# ---------------------------------------------------------------------------
# 13. vertical_normalize — rotation=180 with non-blur modes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_vertical_normalize_rotation_180_crop() -> None:
    """A 1920×1080 clip rotated 180° with mode='crop' prepends transpose×2."""
    result = vertical_normalize(width=1920, height=1080, rotation=180, mode="crop")
    expected = (
        "[0:v]transpose=1,transpose=1,fps=30,"
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=nv12[v]"
    )
    assert result == expected


@pytest.mark.unit
def test_vertical_normalize_rotation_180_bars() -> None:
    """A 1920×1080 clip rotated 180° with mode='bars' prepends transpose×2."""
    result = vertical_normalize(width=1920, height=1080, rotation=180, mode="bars")
    expected = (
        "[0:v]transpose=1,transpose=1,fps=30,"
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,format=nv12[v]"
    )
    assert result == expected


@pytest.mark.unit
def test_vertical_normalize_invalid_mode_raises() -> None:
    """An unrecognized mode raises ValueError."""
    with pytest.raises(ValueError, match="Unknown mode"):
        vertical_normalize(width=1920, height=1080, mode="invalid")  # type: ignore[arg-type]
