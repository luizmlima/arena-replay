from dataclasses import dataclass
from math import isfinite

from .exceptions import InvalidSelectionError


@dataclass(frozen=True, slots=True)
class ClipRange:
    """Half-open interval in seconds, relative to the source video."""

    start: float
    end: float

    def __post_init__(self) -> None:
        if not isfinite(self.start) or not isfinite(self.end):
            raise InvalidSelectionError("Clip boundaries must be finite.")
        if self.start < 0 or self.end <= self.start:
            raise InvalidSelectionError("Expected 0 <= start < end.")

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    codec: str
