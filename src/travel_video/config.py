from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class OutputConfig(BaseModel):
    resolution: str = "1080x1920"
    container: str = "mkv"

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
