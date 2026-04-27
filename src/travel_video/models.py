from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class Clip:
    path: Path
    duration_s: float
    creation_time: datetime
    gps_lat: float | None
    gps_lon: float | None
    rotation: int
    width: int
    height: int

    @property
    def is_vertical(self) -> bool:
        effective_width = self.height if self.rotation in (90, 270) else self.width
        effective_height = self.width if self.rotation in (90, 270) else self.height
        return effective_height >= effective_width

    @property
    def has_gps(self) -> bool:
        return self.gps_lat is not None and self.gps_lon is not None


@dataclass(frozen=True)
class DaySeparator:
    date: date


TimelineItem = Clip | DaySeparator
