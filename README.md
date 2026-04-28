# travel-video-assembler

A CLI tool that turns a folder of raw travel clips into a single polished vertical MKV (1080×1920).

## Requirements

- macOS (Apple Silicon M2+)
- [uv](https://github.com/astral-sh/uv)
- FFmpeg: `brew install ffmpeg`
- ExifTool: `brew install exiftool`

## Installation

```bash
uv sync
```

## Usage

### Render

```bash
uv run travel-video render --input ./input --output ./output/travel.mkv
```

Options:
- `--config PATH` — path to config file (default: `config.yaml`)
- `--dry-run` — print FFmpeg commands without executing
- `--verbose` / `-v` — enable debug logging

### Plan (preview timeline without rendering)

```bash
uv run travel-video plan --input ./input
```

### Inspect (show metadata for one clip)

```bash
uv run travel-video inspect ./input/clip.mp4
```

## Configuration

Copy `config.yaml` and edit as needed:

```yaml
video:
  encoder: h264_videotoolbox  # or hevc_videotoolbox
  bitrate: 12M

transitions:
  clip_crossfade_seconds: 0.5
  day_break_seconds: 3

overlays:
  location_label:
    enabled: true
  mini_map:
    enabled: true
    probability: 0.25
```

## Pipeline

1. **Scan** — detect `.mp4 / .mov / .mkv / .m4v` files, sort by creation date  
2. **Metadata** — extract creation time, GPS, rotation via ExifTool  
3. **Plan** — group by day, insert 3-second black separators between days  
4. **Normalize** — resize every clip to 1080×1920 (blurred background for horizontals)  
5. **Overlays** — bake location label and/or mini-map onto each clip  
6. **Concat** — crossfade all segments together  
7. **Encode** — final MKV via VideoToolbox  

Intermediate artefacts (normalised clips, map tiles) are cached in `.travel_video_cache/` to speed up re-renders.
