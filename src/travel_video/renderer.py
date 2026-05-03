"""renderer.py — orchestrates FFmpeg normalisation and concatenation.

Algorithm
---------
1. For each ``Clip`` in the timeline, normalise to 1080×1920 (cache-aware).
2. For each ``DaySeparator``, generate a black-screen segment (cache-aware).
3. Build an ordered segment list that mirrors the timeline order.
4. Concatenate all segments with xfade transitions.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from travel_video.cache import cache_key, normalized_path
from travel_video.config import Config
from travel_video.ffmpeg import commands
from travel_video.ffmpeg.filters import audio_chain, black_screen, vertical_normalize
from travel_video.models import Clip, DaySeparator, TimelineItem
from travel_video.overlays import location_label, mini_map

log = logging.getLogger(__name__)


def render(
    timeline: list[TimelineItem],
    config: Config,
    output_path: Path,
    *,
    dry_run: bool = False,
    progress_callback: Callable[[], None] | None = None,
) -> None:
    """Render a travel video from *timeline* to *output_path*.

    Parameters
    ----------
    timeline:
        Ordered list of :class:`~travel_video.models.Clip` and
        :class:`~travel_video.models.DaySeparator` items produced by the
        planner.
    config:
        Loaded :class:`~travel_video.config.Config` instance.
    output_path:
        Destination path for the final encoded video.
    dry_run:
        When ``True``, all FFmpeg commands are printed but not executed.
    progress_callback:
        Optional callback invoked when each segment finishes normalisation/generation.
    """
    segments: list[Path] = []

    # Pre-compute the day-separator cache key so duplicates share one file.
    sep_cache_key = (
        f"day_sep_{config.transitions.day_break_seconds}s_"
        f"{config.output.width}x{config.output.height}"
    )

    af = audio_chain(
        config.audio.highpass_hz,
        config.audio.denoise,
        config.audio.loudnorm,
    )

    overlay_sig = hashlib.sha1(
        (
            f"{config.overlays.location_label.enabled}"
            f":{config.overlays.mini_map.enabled}"
            f":{config.overlays.mini_map.probability}"
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:8]

    from concurrent.futures import ThreadPoolExecutor

    def process_item(item: TimelineItem) -> Path:
        if isinstance(item, Clip):
            label_result: tuple[Path, str] | None = None
            if config.overlays.location_label.enabled:
                label_result = location_label.build(item)

            map_result: tuple[Path, str] | None = None
            if config.overlays.mini_map.enabled:
                map_result = mini_map.build(item, config)

            extra_inputs = []
            if label_result:
                extra_inputs.append(label_result[0])
            if map_result:
                extra_inputs.append(map_result[0])

            label_idx = 1 if label_result else None
            map_idx = 1 + (1 if label_result else 0) if map_result else None

            res = _normalize_clip(
                item,
                config,
                af,
                overlay_sig=overlay_sig,
                extra_inputs=extra_inputs,
                label_filter=label_result[1] if label_result else None,
                label_idx=label_idx,
                map_filter=map_result[1] if map_result else None,
                map_idx=map_idx,
                dry_run=dry_run,
            )
        elif isinstance(item, DaySeparator):
            res = _generate_separator(sep_cache_key, config, dry_run=dry_run)
        else:
            raise TypeError(f"Unknown timeline item type: {type(item)}")
            
        if progress_callback:
            progress_callback()
        return res

    # Parallelize normalization using a thread pool.
    # FFmpeg is subprocess-based, so threads are fine for I/O and process management.
    with ThreadPoolExecutor() as executor:
        segments = list(executor.map(process_item, timeline))

    commands.concat_with_xfade(
        segments,
        output_path,
        config.transitions.clip_crossfade_seconds,
        config.video.encoder,
        config.video.bitrate,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalize_clip(
    clip: Clip,
    config: Config,
    af: str,
    *,
    overlay_sig: str = "",
    extra_inputs: list[Path] | None = None,
    label_filter: str | None = None,
    label_idx: int | None = None,
    map_filter: str | None = None,
    map_idx: int | None = None,
    dry_run: bool,
) -> Path:
    """Return the normalized path for *clip*, encoding it if not already cached.

    Parameters
    ----------
    clip:
        Source clip to normalise.
    config:
        Project configuration.
    af:
        Audio filter chain string.
    overlay_sig:
        Short hash of overlay config, appended to the cache key so changes
        in overlay settings bust the cache.
    extra_inputs:
        Additional ``-i`` input paths forwarded to ``normalize_clip``
        (e.g. a mini-map PNG).
    label_filter:
        Overlay filter fragment for location label.
    label_idx:
        Index of the extra input for the label PNG.
    map_filter:
        Overlay filter fragment for the mini map.
    map_idx:
        Index of the extra input for the map PNG.
    dry_run:
        When ``True``, print FFmpeg commands without executing them.
    """
    base_key = cache_key(clip.path)
    key = f"{base_key}_{overlay_sig}" if overlay_sig else base_key
    norm = normalized_path(key)

    if norm.exists():
        log.debug("Cache hit for clip %s → %s", clip.path, norm)
        return norm

    vf = vertical_normalize(clip.width, clip.height, clip.rotation)
    if label_filter or map_filter:
        vf = vf[:-3] + "[v_temp0]"
        current_pad = "[v_temp0]"

        if label_filter and label_idx is not None:
            next_pad = "[v_temp1]" if map_filter else "[v]"
            vf += f";{current_pad}[{label_idx}:v]{label_filter}{next_pad}"
            current_pad = next_pad

        if map_filter and map_idx is not None:
            vf += f";{current_pad}[{map_idx}:v]{map_filter}[v]"

    commands.normalize_clip(
        clip.path,
        norm,
        vf,
        af,
        config.video.encoder,
        config.video.bitrate,
        extra_input_paths=extra_inputs,
        dry_run=dry_run,
        has_audio=clip.has_audio,
    )
    return norm


def _generate_separator(
    sep_key: str,
    config: Config,
    *,
    dry_run: bool,
) -> Path:
    """Return the path to the day-separator black-screen clip, generating it if needed."""
    sep = normalized_path(sep_key)

    if sep.exists():
        log.debug("Cache hit for day separator → %s", sep)
        return sep

    filter_graph = black_screen(
        config.transitions.day_break_seconds,
        config.output.width,
        config.output.height,
    )

    commands.run(
        [
            "-filter_complex",
            filter_graph,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(config.transitions.day_break_seconds),
            "-c:v",
            config.video.encoder,
            "-b:v",
            config.video.bitrate,
            "-c:a",
            "aac",
            str(sep),
        ],
        dry_run=dry_run,
    )
    return sep
