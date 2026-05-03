# travel-video-assembler

A Python CLI tool designed specifically for Apple Silicon Macs to seamlessly assemble a folder of raw travel clips into a single, highly polished vertical travel video (1080×1920).

## Features

- **Automated Layouts:** Intelligently standardizes clips to a `1080x1920` vertical aspect ratio. Horizontal videos automatically receive a dynamic blurred background.
- **Cinematic Transitions:** Applies smooth 0.5s crossfades between clips and inserts a 3-second black screen separator between different days of your trip.
- **Dynamic Overlays:**
  - **Location Labels:** Auto-generates text overlays in the bottom-right corner ("Town, Country, ISO") using reverse geocoding from EXIF GPS data.
  - **Mini-Maps:** Randomly inserts (default 25% chance) a small OpenStreetMap tile in the top-right corner to highlight your travel path.
- **Audio Processing:** Runs a professional normalization pipeline (`highpass` → `afftdn` (denoise) → `loudnorm`) over all clips. Clips without an audio stream (e.g. screen recordings or silent action-cam footage) automatically receive a silent track so they concatenate cleanly.
- **High Performance:** Leverages Apple's native VideoToolbox (`h264_videotoolbox` / `hevc_videotoolbox`) hardware acceleration for rapid rendering, with parallel clip normalization via a thread pool.
- **Smart Caching:** Avoids redundant work by locally caching normalized clips, extracted metadata, generated location labels, and map tiles across runs in `.travel_video_cache/`. Cache entries are automatically invalidated when ExifTool fields or `has_audio` status change, so you never need to manually clear the cache after an update.

---

## Requirements

The pipeline expects a macOS environment, preferably Apple Silicon (M1/M2/M3/M4), due to its heavy reliance on the `_videotoolbox` FFmpeg encoders.

- **[uv](https://github.com/astral-sh/uv)** — Python packaging and execution
- **FFmpeg** — Video processing and encoding
- **ExifTool** — Metadata extraction

### Installation

1. Install system dependencies:
   ```bash
   brew install ffmpeg exiftool uv
   ```

2. Initialize the Python environment and synchronize dependencies:
   ```bash
   uv sync
   ```

---

## Usage

### 1. Render Video

To generate your final travel video, simply drop your `.mp4`, `.mov`, `.mkv`, or `.m4v` files into an `input/` directory and run:

```bash
uv run travel-video render --input ./input --output ./output/travel.mkv
```

**Options:**
- `--config PATH`: Path to a custom config file (default: `config.yaml`).
- `--dry-run`: Prints out the exact FFmpeg commands that will be run, without actually executing them.
- `-v`, `--verbose`: Enable debug logging for tracing metadata extraction, caching logic, and FFmpeg filtergraph construction.

### 2. Plan Timeline (Preview)

Curious about how your clips will be sequenced and sorted before waiting for a render?

```bash
uv run travel-video plan --input ./input
```
*Displays a rich chronological timeline outlining clips, metadata overrides, and inserted day separators.*

### 3. Inspect a Clip

If a clip's rotation, GPS coordinate, or creation date seems wrong, inspect the raw metadata:

```bash
uv run travel-video inspect ./input/clip.MOV
```

---

## Configuration

You can customize almost all pipeline behaviors using `config.yaml`. The schema supports adjusting resolution, encoders, transitions, and overlays.

```yaml
output:
  resolution: "1080x1920"
  container: mkv

video:
  encoder: h264_videotoolbox  # Set to 'hevc_videotoolbox' for smaller H.265 files
  bitrate: 12M

transitions:
  clip_crossfade_seconds: 0.5
  day_break_seconds: 3.0

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

---

## Internal Pipeline Lifecycle

When `render` is called, `travel-video-assembler` proceeds through these distinct steps:

1. **Scan:** Traverses the target directory, discovering valid media files, and sorts them exclusively by their creation date.
2. **Metadata Extraction:** Shells out to `ExifTool` to pull EXIF creation times, duration values, GPS coordinates, and audio stream presence (`AudioChannels`, `AudioFormat`, `AudioSampleRate`). Falls back to file `mtime` when no EXIF date is present.
3. **Planning & Grouping:** Segments clips into distinct travel days based on chronological metadata. Between distinct days, it queues a synthetic 3-second black screen separator.
4. **Normalization & Overlays:** Every clip is processed independently into `.travel_video_cache/`. It guarantees the output is strictly vertical (`1080x1920`), correctly rotated avoiding FFmpeg's autorotate conflicts, enforces exact audio/video synchronization using `-shortest`, and bakes Pillow-generated Location and OpenStreetMap Overlays.
5. **Timeline Composition:** Translates the planned timeline into an exhaustive `xfade` (video) and `acrossfade` (audio) `filter_complex` FFmpeg chain.
6. **Final Render:** Pushes the composition buffer over to macOS VideoToolbox for a lightning-fast hardware encode to an MKV container.

---

## Troubleshooting

- **Geocoding Timeouts (`GeocoderTimedOut`):**
  If internet connection is lost or the Nominatim geocoding service limits your rate, the render will temporarily warn you and skip overlaying the location for those specific clips, gracefully continuing the rest of the rendering.
- **No audio in the output video:**
  This can occur if the metadata cache was written by an older version of the tool (before audio detection was added). The cache now auto-invalidates when ExifTool fields change, so simply re-running the render will rebuild the cache correctly. If you still see no audio, check that `exiftool` can read the source clips with `exiftool -AudioChannels -AudioFormat <clip>`.
- **Audio "Clicks" or Missing Transitions:**
  If crossfades appear as freeze frames, ensure that all input clips are standard variable or constant frame rate. The normalization phase specifically bounds streams with `fps=30` and `-shortest` to prevent track imbalances.
