"""Subprocess layer for FFmpeg and FFprobe invocations.

Builds and runs complete FFmpeg commands from filter fragments produced
by :mod:`travel_video.ffmpeg.filters`.  No filtergraph strings are
constructed here — only the surrounding CLI skeleton.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from travel_video.ffmpeg.filters import crossfade_audio, crossfade_video

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class FFmpegError(RuntimeError):
    """Raised when an FFmpeg or FFprobe process exits with a non-zero code,
    or when its output cannot be parsed."""


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run(args: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[bytes]:
    """Run ``ffmpeg`` with *args*.

    Parameters
    ----------
    args:
        Arguments to pass after the ``ffmpeg`` binary name.
    dry_run:
        When ``True``, print the full command to stdout instead of
        executing it and return a fake :class:`subprocess.CompletedProcess`
        with ``returncode=0``.

    Returns
    -------
    subprocess.CompletedProcess
        The result of the subprocess invocation.

    Raises
    ------
    FFmpegError
        If the process exits with a non-zero return code.
    """
    cmd = ["ffmpeg", *args]

    if dry_run:
        log.info("Dry run: %s", " ".join(str(a) for a in cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    result = subprocess.run(cmd, capture_output=True)  # noqa: S603

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace") if result.stderr else ""
        raise FFmpegError(f"FFmpeg exited with code {result.returncode}. stderr: {stderr}")

    return result


# ---------------------------------------------------------------------------
# FFprobe helper
# ---------------------------------------------------------------------------


def probe_duration(path: Path) -> float:
    """Return the duration of *path* in seconds using ``ffprobe``.

    Parameters
    ----------
    path:
        Path to the media file to probe.

    Returns
    -------
    float
        Duration in seconds.

    Raises
    ------
    FFmpegError
        If ``ffprobe`` exits with a non-zero return code or its output
        cannot be parsed as a float.
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]

    result = subprocess.run(cmd, capture_output=True)  # noqa: S603

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace") if result.stderr else ""
        raise FFmpegError(
            f"ffprobe failed for {path!r} (exit {result.returncode}). stderr: {stderr}"
        )

    raw = result.stdout.decode(errors="replace").strip()

    try:
        return float(raw)
    except ValueError:
        raise FFmpegError(f"Could not parse ffprobe duration output as float: {raw!r}") from None


# ---------------------------------------------------------------------------
# Single-clip normalisation
# ---------------------------------------------------------------------------


def normalize_clip(
    input_path: Path,
    output_path: Path,
    video_filter: str,
    audio_filter: str,
    encoder: str,
    bitrate: str,
    *,
    extra_input_paths: list[Path] | None = None,
    dry_run: bool = False,
) -> None:
    """Normalise a single clip to 1080×1920 with the given filter settings.

    Builds and runs::

        ffmpeg -y -i <input_path> [-i <extra_input> ...]
          -filter_complex "<video_filter>" -map "[v]"
          -af "<audio_filter>"
          -c:v <encoder> -b:v <bitrate>
          -c:a aac
          <output_path>

    Parameters
    ----------
    input_path:
        Source clip.
    output_path:
        Destination path for the normalised clip.
    video_filter:
        Complete ``-filter_complex`` value (must produce a ``[v]`` pad).
    audio_filter:
        Complete ``-af`` value.
    encoder:
        Video encoder name (e.g. ``"h264_videotoolbox"``).
    bitrate:
        Target video bitrate (e.g. ``"12M"``).
    extra_input_paths:
        Optional additional ``-i`` arguments (e.g. map PNG paths) prepended
        before ``-filter_complex``.
    dry_run:
        When ``True``, print the command and skip execution.

    Raises
    ------
    FFmpegError
        If FFmpeg exits with a non-zero return code.
    """
    extra_i_args: list[str] = []
    for extra in extra_input_paths or []:
        extra_i_args.extend(["-i", str(extra)])

    args: list[str] = [
        "-y",
        "-noautorotate",
        "-i",
        str(input_path),
        *extra_i_args,
        "-filter_complex",
        video_filter,
        "-map",
        "[v]",
        "-map",
        "0:a:0?",
        "-af",
        audio_filter,
        "-c:v",
        encoder,
        "-b:v",
        bitrate,
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    run(args, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Multi-clip concatenation with xfade transitions
# ---------------------------------------------------------------------------


def concat_with_xfade(
    inputs: list[Path],
    output: Path,
    xfade_seconds: float,
    encoder: str,
    bitrate: str,
    *,
    dry_run: bool = False,
) -> None:
    """Concatenate multiple clips with xfade transitions between them.

    For *N* = 1: copies the single input to *output* using the given encoder.
    For *N* >= 2: builds an FFmpeg ``-filter_complex`` graph that chains
    ``xfade`` + ``acrossfade`` between each consecutive pair of clips,
    computing the correct timeline offset for each transition.

    The xfade offset for pair *i* (0-based) is::

        offset = sum(duration[0..i-1]) - xfade_seconds * i

    Parameters
    ----------
    inputs:
        Ordered list of input clip paths.
    output:
        Destination path for the concatenated video.
    xfade_seconds:
        Duration of each crossfade transition in seconds.
    encoder:
        Video encoder name (e.g. ``"h264_videotoolbox"``).
    bitrate:
        Target video bitrate (e.g. ``"12M"``).
    dry_run:
        When ``True``, print the command and skip execution.

    Raises
    ------
    FFmpegError
        If FFmpeg exits with a non-zero return code or a duration cannot
        be probed.
    """
    # Build the -i flags
    input_flags: list[str] = []
    for p in inputs:
        input_flags.extend(["-i", str(p)])

    n = len(inputs)

    if n == 1:
        # Single input — just encode/copy to output
        args: list[str] = [
            "-y",
            *input_flags,
            "-c:v",
            encoder,
            "-b:v",
            bitrate,
            "-c:a",
            "aac",
            str(output),
        ]
        run(args, dry_run=dry_run)
        return

    # N >= 2: probe durations for offset computation (only clips 0..N-2 are needed)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor() as executor:
        durations = list(executor.map(probe_duration, inputs[:-1]))

    # Build label pairs and filter fragments.
    # Initially the streams are labelled [0:v]/[0:a], [1:v]/[1:a], …
    filter_parts: list[str] = []

    # Running accumulated duration for offset calculation
    cumulative: float = 0.0

    current_v = "0:v"
    current_a = "0:a"

    for i in range(n - 1):
        next_v = f"{i + 1}:v"
        next_a = f"{i + 1}:a"

        out_v = f"vx{i}"
        out_a = f"ax{i}"

        cumulative += durations[i]
        offset = cumulative - xfade_seconds * (i + 1)

        filter_parts.append(
            crossfade_video(
                duration_s=xfade_seconds,
                offset_s=offset,
                in_label=f"{current_v}][{next_v}",
                out_label=out_v,
            )
        )
        filter_parts.append(
            crossfade_audio(
                duration_s=xfade_seconds,
                offset_s=offset,
                in_label=f"{current_a}][{next_a}",
                out_label=out_a,
            )
        )

        current_v = out_v
        current_a = out_a

    filter_complex = ";".join(filter_parts)

    args = [
        "-y",
        *input_flags,
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{current_v}]",
        "-map",
        f"[{current_a}]",
        "-c:v",
        encoder,
        "-b:v",
        bitrate,
        "-c:a",
        "aac",
        str(output),
    ]
    run(args, dry_run=dry_run)
