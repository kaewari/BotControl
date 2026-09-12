"""Persistent UI Coordinate & Button Cache with Self-Healing Fallbacks."""
import os
import json
import time
import logging
from typing import Dict, Optional, Tuple
from bot.core.coordinates import Point, BoundingBox

logger = logging.getLogger("BotControl.Cache")

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ui_cache.json")

# Calibrated baseline coordinates for iPad Pro 13-inch (M5)
DEFAULT_CACHE = {
    "phone_menu_icon": {"x": 0.040, "y": 0.050, "label": "Menu Điện Thoại"},
    "phone_assignments": {"x": 0.887, "y": 0.354, "label": "Ủy Thác"},
    "guidebook_icon": {"x": 0.790, "y": 0.050, "label": "Sổ Tay Sinh Tồn"},
    "guidebook_close": {"x": 0.963, "y": 0.065, "label": "Đóng Sổ Tay"},
    "tab_daily_training": {"x": 0.150, "y": 0.245, "label": "Tab Huấn Luyện Thường Ngày"},
    "tab_survival_index": {"x": 0.215, "y": 0.245, "label": "Tab Hướng Dẫn Sinh Tồn"},
    "tab_simulated_universe": {"x": 0.285, "y": 0.245, "label": "Tab Vũ Trụ Mô Phỏng"},
    "chest_100": {"x": 0.310, "y": 0.358, "label": "Mốc Rương 100"},
    "chest_200": {"x": 0.454, "y": 0.357, "label": "Mốc Rương 200"},
    "chest_300": {"x": 0.598, "y": 0.357, "label": "Mốc Rương 300"},
    "chest_400": {"x": 0.742, "y": 0.358, "label": "Mốc Rương 400"},
    "chest_500": {"x": 0.886, "y": 0.357, "label": "Mốc Rương 500"},
    "target_relic_enter": {"x": 0.854, "y": 0.536, "label": "Vào Di Vật Hang Động"},
    "target_planar_enter_1": {"x": 0.871, "y": 0.684, "label": "Vào Phụ Kiện Vị Diện 1"},
    "dungeon_challenge_btn": {"x": 0.869, "y": 0.910, "label": "Nút Khiêu Chiến (Phó bản)"},
    "team_start_battle_btn": {"x": 0.841, "y": 0.909, "label": "Nút Bắt Đầu Khiêu Chiến (Đội hình)"},
    "battle_retreat_btn": {"x": 0.350, "y": 0.900, "label": "Nút Rút Lui (Chiến thắng)"},
    "resin_popup_cancel": {"x": 0.376, "y": 0.667, "label": "Nút Hủy (Popup bổ sung nhựa)"},
    "back_button": {"x": 0.045, "y": 0.055, "label": "Nút Quay Lại"},
}


class UICoordinateCache:
    """Manages persistent caching and lookup of game UI button coordinates."""

    def __init__(self, filepath: str = CACHE_FILE):
        self.filepath = filepath
        self.cache: Dict[str, dict] = {}
        self.load()

    def load(self):
        """Loads cached coordinates from JSON, merging with calibrated defaults."""
        self.cache = dict(DEFAULT_CACHE)
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.cache.update(loaded)
                logger.info(f"Đã nạp {len(self.cache)} vị trí nút bấm từ {self.filepath}")
            except Exception as e:
                logger.warning(f"Không thể đọc file cache {self.filepath}: {e}")
        else:
            self.save()

    def save(self):
        """Persists current cache to disk."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            logger.debug(f"Đã lưu cache vào {self.filepath}")
        except Exception as e:
            logger.error(f"Lỗi khi lưu cache {self.filepath}: {e}")

    def get_point(self, key: str) -> Optional[Point]:
        """Returns normalized Point from cache if exists."""
        entry = self.cache.get(key)
        if entry and "x" in entry and "y" in entry:
            return Point(float(entry["x"]), float(entry["y"]))
        return None

    def get_box(self, key: str) -> Optional[BoundingBox]:
        """Returns BoundingBox from cache if exists."""
        entry = self.cache.get(key)
        if entry and "box" in entry:
            b = entry["box"]
            return BoundingBox(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        return None

    def update(self, key: str, x: float, y: float, box: Optional[BoundingBox] = None, label: str = ""):
        """Updates or learns a new button position."""
        entry = {
            "x": round(float(x), 4),
            "y": round(float(y), 4),
            "label": label or self.cache.get(key, {}).get("label", key),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if box:
            entry["box"] = [round(box.x1, 1), round(box.y1, 1), round(box.x2, 1), round(box.y2, 1)]
        self.cache[key] = entry
        self.save()
        logger.info(f"Đã cập nhật cache cho nút '{key}': ({entry['x']}, {entry['y']})")


# Singleton instance
ui_cache = UICoordinateCache()
