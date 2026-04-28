"""location_label.py — Pillow-based overlay for reverse-geocoded location.

Renders "Town, Country, ISO" text in the bottom-right corner of a clip.
Returns None when GPS data is unavailable or geocoding fails.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from travel_video import cache
from travel_video.geocode import reverse
from travel_video.models import Clip


def build(clip: Clip, *, margin: int = 48) -> tuple[Path, str] | None:
    """Return a generated PNG path and overlay fragment, or None if no GPS.

    Format: "Town, Country, ISO"
    Position: bottom-right with *margin* px from edges
    Style: white text, semi-transparent black box

    Args:
        clip:   The source clip whose GPS coordinates are used.
        margin: Pixel distance from the right and bottom edges.

    Returns:
        A tuple of ``(png_path, overlay_fragment)``, or ``None`` when GPS
        is absent or reverse-geocoding returns no result.
    """
    if clip.gps_lat is None or clip.gps_lon is None:
        return None

    location = reverse(clip.gps_lat, clip.gps_lon)
    if location is None:
        return None

    label = f"{location.town}, {location.country}, {location.iso}"
    
    key = f"{cache.cache_key(clip.path)}_label"
    png_path = cache.map_path(key)

    if not png_path.exists():
        font_size = 42
        try:
            font = ImageFont.truetype("Arial", font_size)
        except OSError:
            font = ImageFont.load_default()

        dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bbox = dummy_draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad = 12
        img_w = text_w + pad * 2
        img_h = text_h + pad * 2
        
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 128))
        draw = ImageDraw.Draw(img)
        draw.text((pad, pad - bbox[1]), label, font=font, fill=(255, 255, 255, 255))
        png_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(png_path)

    return png_path, f"overlay=W-w-{margin}:H-h-{margin}"
