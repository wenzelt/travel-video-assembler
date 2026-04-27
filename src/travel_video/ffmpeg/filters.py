"""Pure functions that build FFmpeg filtergraph strings.

No subprocess calls — every function returns a string only.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TARGET_W = 1080
_TARGET_H = 1920

_BLUR_GRAPH = (
    "[0:v]split=2[bg][fg];"
    f"[bg]scale={_TARGET_W}:{_TARGET_H}:force_original_aspect_ratio=increase,"
    f"crop={_TARGET_W}:{_TARGET_H},boxblur=20:20[bg2];"
    f"[fg]scale={_TARGET_W}:{_TARGET_H}:force_original_aspect_ratio=decrease[fg2];"
    "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[v]"
)

_TRANSPOSE_PREFIX: dict[int, str] = {
    90: "transpose=1,",
    180: "transpose=1,transpose=1,",
    270: "transpose=2,",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def vertical_normalize(
    width: int,
    height: int,
    rotation: int = 0,
    mode: str = "blur",
) -> str:
    """Return a filtergraph string that converts any clip to 1080×1920.

    Parameters
    ----------
    width:
        Source clip pixel width (before rotation).
    height:
        Source clip pixel height (before rotation).
    rotation:
        EXIF/container rotation in degrees (0, 90, 180, or 270).
    mode:
        One of ``"blur"`` (default), ``"crop"``, or ``"bars"``.

    Returns
    -------
    str
        FFmpeg filtergraph fragment.  The label ``[v]`` is always the
        final output pad.
    """
    # Determine prefix for rotate transposes
    transpose_prefix = _TRANSPOSE_PREFIX.get(rotation, "")

    # After rotation, logical width/height may swap
    if rotation in (90, 270):
        eff_w, eff_h = height, width
    else:
        eff_w, eff_h = width, height

    already_vertical = eff_h >= eff_w

    if already_vertical:
        core = f"scale={_TARGET_W}:{_TARGET_H}[v]"
    elif mode == "crop":
        core = (
            f"scale={_TARGET_W}:{_TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={_TARGET_W}:{_TARGET_H}[v]"
        )
    elif mode == "bars":
        core = (
            f"scale={_TARGET_W}:{_TARGET_H}:force_original_aspect_ratio=decrease,"
            f"pad={_TARGET_W}:{_TARGET_H}:(ow-iw)/2:(oh-ih)/2:black[v]"
        )
    else:
        # "blur" is the default
        core = _BLUR_GRAPH

    return f"{transpose_prefix}{core}"


def audio_chain(
    highpass_hz: int = 120,
    denoise: str | None = "afftdn",
    loudnorm: bool = True,
) -> str:
    """Return a comma-joined audio filtergraph string.

    Parameters
    ----------
    highpass_hz:
        High-pass filter cutoff frequency in Hz.  Always included.
    denoise:
        Denoise filter name (e.g. ``"afftdn"``).  Pass ``None`` or ``""``
        to omit.
    loudnorm:
        When ``True`` the ``loudnorm`` filter is appended.

    Returns
    -------
    str
        Comma-joined FFmpeg audio filter chain.
    """
    parts: list[str] = [f"highpass=f={highpass_hz}"]
    if denoise:
        parts.append(denoise)
    if loudnorm:
        parts.append("loudnorm")
    return ",".join(parts)


def crossfade_video(
    duration_s: float,
    offset_s: float,
    in_label: str,
    out_label: str,
) -> str:
    """Return an xfade filtergraph string for video crossfade.

    Parameters
    ----------
    duration_s:
        Crossfade duration in seconds.
    offset_s:
        Timeline offset (start of crossfade) in seconds.
    in_label:
        Input pad label (without brackets).
    out_label:
        Output pad label (without brackets).

    Returns
    -------
    str
        FFmpeg xfade filter fragment.
    """
    return (
        f"[{in_label}]xfade=transition=fade:"
        f"duration={duration_s}:offset={offset_s}[{out_label}]"
    )


def crossfade_audio(
    duration_s: float,
    offset_s: float,  # noqa: ARG001  — kept for API symmetry with crossfade_video
    in_label: str,
    out_label: str,
) -> str:
    """Return an acrossfade filtergraph string for audio crossfade.

    Parameters
    ----------
    duration_s:
        Crossfade duration in seconds.
    offset_s:
        Accepted for API symmetry with :func:`crossfade_video`; not used
        by ``acrossfade``.
    in_label:
        Input pad label (without brackets).
    out_label:
        Output pad label (without brackets).

    Returns
    -------
    str
        FFmpeg acrossfade filter fragment.
    """
    return f"[{in_label}]acrossfade=d={duration_s}:c1=tri:c2=tri[{out_label}]"


def black_screen(
    duration_s: float = 3.0,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Return a filtergraph that generates a silent black screen segment.

    Produces both a ``[v]`` video stream and an ``[a]`` audio stream so the
    segment can be concatenated with real clips.

    Parameters
    ----------
    duration_s:
        Length of the black screen in seconds.
    width:
        Frame width in pixels.
    height:
        Frame height in pixels.

    Returns
    -------
    str
        FFmpeg filtergraph fragment (video and audio separated by ``;``).
    """
    return (
        f"color=c=black:s={width}x{height}:d={duration_s}:r=30[v];"
        f"aevalsrc=0:d={duration_s}[a]"
    )
