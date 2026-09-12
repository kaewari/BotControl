"""Coordinate system and geometry utilities for iPad Pro automation."""
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Point:
    x: float
    y: float

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def to_int_tuple(self) -> Tuple[int, int]:
        return (int(round(self.x)), int(round(self.y)))


@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> Point:
        return Point((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def contains(self, p: Point) -> bool:
        return self.x1 <= p.x <= self.x2 and self.y1 <= p.y <= self.y2

    def to_int_coords(self) -> Tuple[int, int, int, int]:
        return (int(round(self.x1)), int(round(self.y1)), int(round(self.x2)), int(round(self.y2)))


class CoordinateSystem:
    """Manages scaling between normalized [0.0 - 1.0] and screen physical pixel coordinates."""

    def __init__(self, screen_width: int = 2752, screen_height: int = 2064):
        self.screen_width = screen_width
        self.screen_height = screen_height

    def update_resolution(self, width: int, height: int):
        self.screen_width = width
        self.screen_height = height

    def norm_to_abs_point(self, p: Point) -> Point:
        """Converts normalized Point (0.0 - 1.0) to absolute device pixels."""
        return Point(p.x * self.screen_width, p.y * self.screen_height)

    def abs_to_norm_point(self, p: Point) -> Point:
        """Converts absolute pixel Point to normalized Point (0.0 - 1.0)."""
        if self.screen_width == 0 or self.screen_height == 0:
            return Point(0.0, 0.0)
        return Point(p.x / self.screen_width, p.y / self.screen_height)

    def norm_to_abs_box(self, box: BoundingBox) -> BoundingBox:
        """Converts normalized BoundingBox to absolute pixel BoundingBox."""
        return BoundingBox(
            x1=box.x1 * self.screen_width,
            y1=box.y1 * self.screen_height,
            x2=box.x2 * self.screen_width,
            y2=box.y2 * self.screen_height,
        )

    def abs_to_norm_box(self, box: BoundingBox) -> BoundingBox:
        """Converts absolute pixel BoundingBox to normalized BoundingBox."""
        return BoundingBox(
            x1=box.x1 / self.screen_width,
            y1=box.y1 / self.screen_height,
            x2=box.x2 / self.screen_width,
            y2=box.y2 / self.screen_height,
        )


# Common normalized zones for Honkai: Star Rail on iPad
class HSRZones:
    # Safe tap zone for skipping dialogues without accidentally clicking choices
    DIALOGUE_SAFE_TAP = Point(0.85, 0.70)

    # Top-right Skip button (Bỏ qua hội thoại)
    DIALOGUE_SKIP_BUTTON = BoundingBox(0.86, 0.03, 0.98, 0.10)

    # Battle Top-Right: Auto-Battle Toggle & 2x Speed Toggle
    BATTLE_AUTO_TOGGLE = BoundingBox(0.88, 0.02, 0.95, 0.09)
    BATTLE_SPEED_TOGGLE = BoundingBox(0.82, 0.02, 0.88, 0.09)
    BATTLE_PAUSE_BUTTON = BoundingBox(0.95, 0.02, 0.99, 0.09)

    # Top Navigation: Guidebook (Sổ tay hướng dẫn)
    GUIDEBOOK_ICON = BoundingBox(0.78, 0.02, 0.84, 0.09)

    # Battle End Results
    REPEAT_CHALLENGE_BUTTON = BoundingBox(0.55, 0.88, 0.88, 0.96)
    EXIT_BATTLE_BUTTON = BoundingBox(0.12, 0.88, 0.45, 0.96)
