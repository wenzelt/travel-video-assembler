# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`travel-video-assembler` — a Python CLI that turns a folder of raw travel clips into a single polished vertical MKV.

## Commands

```bash
# Run the CLI
uv run travel-video render --input ./input --output ./output/travel.mkv
uv run travel-video plan
uv run travel-video inspect <file>

# Lint
uv run ruff check .
uv run ruff format .

# Tests
uv run pytest
uv run pytest tests/test_metadata.py          # single file
uv run pytest -k "test_group_by_day"          # single test
uv run pytest --cov=travel_video --cov-report=term-missing
```

## Architecture

The pipeline is a strict linear sequence of steps, each handled by its own module:

```
scanner → metadata → planner → renderer
```

1. **`scanner.py`** — walks `input/`, detects video files, returns sorted paths
2. **`metadata.py`** — calls ExifTool (`subprocess`) per clip, populates `Clip` dataclass (path, duration, creation_time, gps_lat, gps_lon, rotation); falls back to `os.path.getmtime` when EXIF is absent
3. **`planner.py`** — groups `Clip` objects by calendar date, inserts `DaySeparator` sentinel objects between groups; output is the ordered timeline passed to the renderer
4. **`renderer.py`** — orchestrates FFmpeg: normalises each clip to 1080×1920 (blurred background for horizontals), bakes overlays, splices transitions, and performs the final encode; reads `config.yaml` for all tunable parameters

### Overlays (`overlays/`)

Each overlay is a self-contained module that produces an FFmpeg filter-graph fragment:

- **`location_label.py`** — renders `Town, Country, ISO` text bottom-right using `geocode.py` (reverse-geocodes GPS with `geopy`)
- **`mini_map.py`** — renders a static map tile top-right; applied with configurable probability (default 25%)
- **`day_separator.py`** — produces the 3-second black screen between days

### FFmpeg layer (`ffmpeg/`)

- **`filters.py`** — pure functions that build `filtergraph` strings (scale, pad, blur, crossfade, audio chain `highpass→afftdn→loudnorm`)
- **`commands.py`** — assembles complete `ffmpeg` invocations from filter fragments and runs them via `subprocess`

### Caching

Intermediate artefacts are stored in `.travel_video_cache/` (metadata JSON, map tiles, normalised clips). Cache keys are based on source file path + mtime; modules check the cache before invoking ExifTool or FFmpeg.

## Key Constraints

- **Platform**: macOS Apple Silicon M2 only — video encoder is `h264_videotoolbox` (or `hevc_videotoolbox`); do not add CPU-encoder fallbacks unless asked.
- **Output**: always 1080×1920 vertical MKV. Horizontal clips get blurred-background fill; crop and black-bar modes exist as config options but are not the default.
- **Transitions**: 0.5 s crossfade between clips; 3 s black screen between days (not a crossfade).
- **Audio**: `highpass=f=120,afftdn,loudnorm` applied to every clip before concatenation.
- **Config**: all tunable values live in `config.yaml` — nothing is hardcoded in Python.

## Configuration (`config.yaml`)

```yaml
output:
  resolution: "1080x1920"
  container: mkv
video:
  encoder: h264_videotoolbox
  bitrate: 12M
transitions:
  clip_crossfade_seconds: 0.5
  day_break_seconds: 3
audio:
  highpass_hz: 120
  denoise: afftdn
  loudnorm: true
overlays:
  location_label:
    enabled: true
    position: bottom_right
  mini_map:
    enabled: true
    probability: 0.25
```
