from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class OutputConfig(BaseModel):
    resolution: str = "1080x1920"
    container: str = "mkv"

    @field_validator("resolution")
    @classmethod
    def _check_resolution(cls, v: str) -> str:
        if not v or "x" not in v:
            raise ValueError(f"resolution must be WxH, got {v!r}")
        parts = v.split("x")
        if len(parts) != 2:
            raise ValueError(f"resolution must have exactly one 'x', got {v!r}")
        try:
            w = int(parts[0])
            h = int(parts[1])
        except ValueError:
            raise ValueError(f"resolution parts must be integers, got {v!r}") from None
        
        if w <= 0 or h <= 0:
            raise ValueError(f"resolution dimensions must be positive, got {w}x{h}")
        return f"{w}x{h}"

    @property
    def width(self) -> int:
        return int(self.resolution.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.resolution.split("x")[1])


class VideoConfig(BaseModel):
    encoder: str = "h264_videotoolbox"
    bitrate: str = "12M"


class TransitionsConfig(BaseModel):
    clip_crossfade_seconds: float = 0.5
    day_break_seconds: float = 3.0


class AudioConfig(BaseModel):
    highpass_hz: int = 120
    denoise: str = "afftdn"
    loudnorm: bool = True


class OverlayItemConfig(BaseModel):
    enabled: bool = True
    position: str = "bottom_right"
    probability: float = Field(default=0.25, ge=0.0, le=1.0)


class OverlaysConfig(BaseModel):
    location_label: OverlayItemConfig = Field(default_factory=OverlayItemConfig)
    mini_map: OverlayItemConfig = Field(
        default_factory=lambda: OverlayItemConfig(position="top_right")
    )


class Config(BaseModel):
    output: OutputConfig = Field(default_factory=OutputConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    transitions: TransitionsConfig = Field(default_factory=TransitionsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    overlays: OverlaysConfig = Field(default_factory=OverlaysConfig)

    @classmethod
    def load(cls, path: Path) -> Config:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
