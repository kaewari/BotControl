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


class HSRZones:
    """Accurate normalized coordinates derived from iPad Pro 13-inch (M5) screenshots."""

    # Top-Level Main Screen Shortcuts
    PHONE_MENU_ICON = Point(0.04, 0.05)       # Top-left Phone menu
    BACK_BUTTON = Point(0.045, 0.055)         # Back arrow
    GUIDEBOOK_ICON = Point(0.79, 0.05)        # Top-right Peace Guide icon
    MAP_ICON = Point(0.92, 0.05)              # Top-right Map icon
    INVENTORY_ICON = Point(0.85, 0.05)        # Top-right Bag icon

    # Guidebook Top Bar
    GUIDEBOOK_CLOSE = Point(0.963, 0.065)     # Close 'X' button
    RESIN_COUNTER_BOX = BoundingBox(0.70, 0.03, 0.82, 0.09)  # Trailblaze Power indicator (e.g. 164/300)
    FUEL_COUNTER_BOX = BoundingBox(0.62, 0.03, 0.68, 0.09)   # Fuel flasks indicator (e.g. 11)

    # 5 Major Top Tabs inside Guidebook
    TAB_DAILY_TRAINING = Point(0.148, 0.245)      # Huấn Luyện Thường Ngày
    TAB_SURVIVAL_INDEX = Point(0.218, 0.245)      # Hướng Dẫn Sinh Tồn
    TAB_SIMULATED_UNIVERSE = Point(0.288, 0.245)  # Vũ Trụ Mô Phỏng / Sai Phân
    TAB_ENDGAME_CHALLENGE = Point(0.358, 0.245)   # Sảnh Đường / Kỷ Sự
    TAB_EVENTS = Point(0.428, 0.245)              # Biến Cố / Sự Kiện

    # Survival Index Left Category Items
    LEFT_NAV_TARGET_CHARACTER = Point(0.20, 0.35)  # Mục Tiêu Bồi Dưỡng (Robin, v.v.)
    LEFT_NAV_PLANAR = Point(0.20, 0.45)            # Trích Xuất Phụ Kiện
    LEFT_NAV_CALYX_GOLDEN = Point(0.20, 0.55)      # Đài Hoa Nhân Tạo (Vàng)
    LEFT_NAV_CALYX_CRIMSON = Point(0.20, 0.65)     # Đài Hoa Nhân Tạo (Đỏ)
    LEFT_NAV_STAGNANT_SHADOW = Point(0.20, 0.75)   # Hư Ảnh Ngưng Đọng
    LEFT_NAV_CAVERN_CORROSION = Point(0.20, 0.82)  # Vết Tích Xâm Thực (kéo xuống)
    LEFT_NAV_ECHO_OF_WAR = Point(0.20, 0.90)       # Dư Âm Chiến Đấu (kéo xuống)

    # Action Buttons on Dungeon Rows (Vào / Enter buttons are aligned at X ≈ 0.854)
    ENTER_ROW_1 = Point(0.854, 0.399)             # Nút Vào hàng 1
    ENTER_ROW_2 = Point(0.854, 0.548)             # Nút Vào hàng 2
    ENTER_ROW_3 = Point(0.854, 0.653)             # Nút Vào hàng 3
    ENTER_ROW_4 = Point(0.854, 0.760)             # Nút Vào hàng 4

    # Character Target Quick Actions (Mục Tiêu Bồi Dưỡng)
    TARGET_RELIC_ENTER = Point(0.854, 0.468)       # Vào Đề Xuất Di Vật Hang Động
    TARGET_PLANAR_ENTER_1 = Point(0.854, 0.616)    # Vào Đề Xuất Phụ Kiện 1
    TARGET_PLANAR_ENTER_2 = Point(0.849, 0.721)    # Vào Đề Xuất Phụ Kiện 2

    # Dialogue Interaction
    DIALOGUE_SAFE_TAP = Point(0.85, 0.70)
    DIALOGUE_SKIP_BUTTON = BoundingBox(0.86, 0.03, 0.98, 0.10)
    DIALOGUE_CHOICE_1 = Point(0.72, 0.50)

    # Battle Controls
    BATTLE_AUTO_TOGGLE = BoundingBox(0.88, 0.02, 0.95, 0.09)
    BATTLE_SPEED_TOGGLE = BoundingBox(0.82, 0.02, 0.88, 0.09)
    BATTLE_PAUSE_BUTTON = BoundingBox(0.95, 0.02, 0.99, 0.09)
    REPEAT_CHALLENGE_BUTTON = BoundingBox(0.55, 0.88, 0.88, 0.96)
    EXIT_BATTLE_BUTTON = BoundingBox(0.12, 0.88, 0.45, 0.96)

    # 3D Overworld Navigation & Interaction (iPad Pro 13" M5 4:3)
    MINIMAP_BOUNDS = BoundingBox(0.015, 0.025, 0.165, 0.225)
    JOYSTICK_CENTER = Point(0.185, 0.765)
    JOYSTICK_MAX_RADIUS = 0.080
    CAMERA_SWIPE_ZONE = BoundingBox(0.40, 0.25, 0.85, 0.70)
    INTERACTION_PROMPT_BOX = BoundingBox(0.60, 0.40, 0.82, 0.65)
    SPRINT_BUTTON = Point(0.925, 0.890)
    ATTACK_BUTTON = Point(0.835, 0.830)

