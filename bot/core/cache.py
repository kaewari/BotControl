"""Persistent UI Coordinate & Button Cache with Self-Healing Fallbacks for iPad Pro 13" M5."""
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from bot.core.coordinates import BoundingBox, Point
from bot.cv.ocr_service import OCRService, normalize_text, remove_vietnamese_tones

logger = logging.getLogger("BotControl.Cache")

CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ui_cache.json"
)

# Standard metadata for iPad Pro 13-inch (M5)
DEFAULT_META: Dict[str, Any] = {
    "version": "2.0.0",
    "device": "iPad Pro 13-inch (M5)",
    "screen_width": 2752,
    "screen_height": 2064,
    "aspect_ratio": "4:3",
    "updated_at": "2026-09-12 16:30:00",
}

# 28 Calibrated baseline coordinates & bounding boxes for iPad Pro 13-inch (M5)
DEFAULT_CACHE: Dict[str, Dict[str, Any]] = {
    "phone_menu_icon": {
        "x": 0.0400,
        "y": 0.0500,
        "box": [0.0150, 0.0250, 0.0650, 0.0750],
        "label": "Menu Điện Thoại",
        "expected_keywords": [],
    },
    "phone_assignments": {
        "x": 0.8870,
        "y": 0.3540,
        "box": [0.8350, 0.3200, 0.9400, 0.3880],
        "label": "Ủy Thác",
        "expected_keywords": ["Ủy Thác", "Uy Thac", "Thác"],
    },
    "assignment_claim_all": {
        "x": 0.7980,
        "y": 0.7840,
        "box": [0.7420, 0.7700, 0.8540, 0.7980],
        "label": "Nhận Tất Cả",
        "expected_keywords": ["Nhận Tất Cả", "Nhan Tat Ca", "Nhận Thưởng", "Nhan Thuong", "Nhận", "Nhan"],
    },
    "assignment_redispatch": {
        "x": 0.8100,
        "y": 0.8600,
        "box": [0.7300, 0.8300, 0.8900, 0.8900],
        "label": "Phái Lại Tất Cả",
        "expected_keywords": ["Phái Lại", "Phai Lai", "Phái lại tất cả", "Phái", "Phai"],
    },
    "guidebook_icon": {
        "x": 0.7900,
        "y": 0.0500,
        "box": [0.7600, 0.0250, 0.8200, 0.0750],
        "label": "Sổ Tay Sinh Tồn",
        "expected_keywords": [],
    },
    "guidebook_close": {
        "x": 0.9630,
        "y": 0.0650,
        "box": [0.9400, 0.0400, 0.9850, 0.0900],
        "label": "Đóng Sổ Tay",
        "expected_keywords": [],
    },
    "tab_daily_training": {
        "x": 0.1500,
        "y": 0.2450,
        "box": [0.0900, 0.2200, 0.2100, 0.2700],
        "label": "Tab Huấn Luyện Thường Ngày",
        "expected_keywords": ["Huấn Luyện", "Huan Luyen", "Thường Ngày", "Thuong Ngay"],
    },
    "tab_survival_index": {
        "x": 0.2150,
        "y": 0.2450,
        "box": [0.1800, 0.2200, 0.2550, 0.2700],
        "label": "Tab Hướng Dẫn Sinh Tồn",
        "expected_keywords": ["Hướng Dẫn", "Huong Dan", "Sinh Tồn", "Sinh Ton"],
    },
    "tab_simulated_universe": {
        "x": 0.2850,
        "y": 0.2450,
        "box": [0.2500, 0.2200, 0.3200, 0.2700],
        "label": "Tab Vũ Trụ Mô Phỏng",
        "expected_keywords": ["Vũ Trụ", "Vu Tru", "Mô Phỏng", "Mo Phong"],
    },
    "chest_100": {
        "x": 0.3105,
        "y": 0.3577,
        "box": [0.2969, 0.3464, 0.3241, 0.3690],
        "label": "Mốc Rương 100",
        "expected_keywords": ["100"],
    },
    "chest_200": {
        "x": 0.4536,
        "y": 0.3574,
        "box": [0.4395, 0.3464, 0.4677, 0.3684],
        "label": "Mốc Rương 200",
        "expected_keywords": ["200"],
    },
    "chest_300": {
        "x": 0.5978,
        "y": 0.3574,
        "box": [0.5837, 0.3464, 0.6119, 0.3684],
        "label": "Mốc Rương 300",
        "expected_keywords": ["300"],
    },
    "chest_400": {
        "x": 0.7419,
        "y": 0.3577,
        "box": [0.7278, 0.3464, 0.7560, 0.3690],
        "label": "Mốc Rương 400",
        "expected_keywords": ["400"],
    },
    "chest_500": {
        "x": 0.8861,
        "y": 0.3574,
        "box": [0.8720, 0.3464, 0.9002, 0.3684],
        "label": "Mốc Rương 500",
        "expected_keywords": ["500"],
    },
    "daily_mission_claim": {
        "x": 0.1915,
        "y": 0.7294,
        "box": [0.1719, 0.7174, 0.2112, 0.7414],
        "label": "Nhận Thưởng Nhiệm Vụ",
        "expected_keywords": ["Nhận", "Nhan"],
    },
    "target_character_card": {
        "x": 0.1772,
        "y": 0.3665,
        "box": [0.1123, 0.3555, 0.2422, 0.3776],
        "label": "Thẻ Nhân Vật (Robin)",
        "expected_keywords": ["Robin", "Mục Tiêu", "Muc Tieu"],
    },
    "target_relic_enter": {
        "x": 0.8540,
        "y": 0.4681,
        "box": [0.8379, 0.4557, 0.8701, 0.4805],
        "label": "Vào Di Vật Hang Động (Robin)",
        "expected_keywords": ["Vào", "Vao"],
    },
    "target_planar_enter_1": {
        "x": 0.8594,
        "y": 0.6159,
        "box": [0.8320, 0.6042, 0.8867, 0.6276],
        "label": "Vào Phụ Kiện Vị Diện 1 (Robin)",
        "expected_keywords": ["Vào", "Vao"],
    },
    "target_planar_enter_2": {
        "x": 0.8491,
        "y": 0.7214,
        "box": [0.8096, 0.7070, 0.8887, 0.7357],
        "label": "Vào Phụ Kiện Vị Diện 2 (Robin)",
        "expected_keywords": ["Vào", "Vao"],
    },
    "enter_row_1": {
        "x": 0.8545,
        "y": 0.3991,
        "box": [0.8389, 0.3867, 0.8701, 0.4115],
        "label": "Vào Hàng 1",
        "expected_keywords": ["Vào", "Vao"],
    },
    "enter_row_2": {
        "x": 0.8550,
        "y": 0.5475,
        "box": [0.8389, 0.5339, 0.8711, 0.5612],
        "label": "Vào Hàng 2",
        "expected_keywords": ["Vào", "Vao"],
    },
    "enter_row_3": {
        "x": 0.8545,
        "y": 0.6530,
        "box": [0.8389, 0.6406, 0.8701, 0.6654],
        "label": "Vào Hàng 3",
        "expected_keywords": ["Vào", "Vao"],
    },
    "enter_row_4": {
        "x": 0.8545,
        "y": 0.7598,
        "box": [0.8389, 0.7474, 0.8701, 0.7721],
        "label": "Vào Hàng 4",
        "expected_keywords": ["Vào", "Vao"],
    },
    "dungeon_challenge_btn": {
        "x": 0.8690,
        "y": 0.9100,
        "box": [0.8200, 0.8800, 0.9200, 0.9400],
        "label": "Nút Khiêu Chiến (Phó bản)",
        "expected_keywords": ["Khiêu Chiến", "Khieu Chien"],
    },
    "team_start_battle_btn": {
        "x": 0.8410,
        "y": 0.9090,
        "box": [0.7900, 0.8800, 0.8950, 0.9400],
        "label": "Nút Bắt Đầu Khiêu Chiến (Đội hình)",
        "expected_keywords": ["Bắt Đầu", "Bat Dau", "Khiêu Chiến", "Khieu Chien"],
    },
    "battle_retreat_btn": {
        "x": 0.3500,
        "y": 0.9000,
        "box": [0.2500, 0.8700, 0.4500, 0.9300],
        "label": "Nút Rút Lui (Chiến thắng)",
        "expected_keywords": ["Rút Lui", "Rut Lui"],
    },
    "resin_popup_cancel": {
        "x": 0.3760,
        "y": 0.6670,
        "box": [0.3200, 0.6450, 0.4350, 0.6900],
        "label": "Nút Hủy (Popup bổ sung nhựa)",
        "expected_keywords": ["Hủy", "Huy"],
    },
    "back_button": {
        "x": 0.0450,
        "y": 0.0550,
        "box": [0.0200, 0.0300, 0.0700, 0.0800],
        "label": "Nút Quay Lại",
        "expected_keywords": [],
    },
}


@dataclass
class UIElement:
    """Represents a cached UI element with normalized coordinates, bounding box, and verification metadata."""

    key: str
    x: float
    y: float
    box: Optional[BoundingBox] = None
    label: str = ""
    expected_keywords: List[str] = field(default_factory=list)
    verified_count: int = 0
    last_verified: str = ""

    @property
    def point(self) -> Point:
        return Point(self.x, self.y)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "x": round(float(self.x), 4),
            "y": round(float(self.y), 4),
            "label": self.label,
            "expected_keywords": list(self.expected_keywords),
            "verified_count": int(self.verified_count),
            "last_verified": self.last_verified,
        }
        if self.box is not None:
            d["box"] = [
                round(float(self.box.x1), 4),
                round(float(self.box.y1), 4),
                round(float(self.box.x2), 4),
                round(float(self.box.y2), 4),
            ]
        return d

    @classmethod
    def from_dict(cls, key: str, data: dict) -> "UIElement":
        box = None
        if "box" in data and data["box"] is not None:
            b = data["box"]
            if isinstance(b, BoundingBox):
                box = b
            elif isinstance(b, (list, tuple)) and len(b) >= 4:
                box = BoundingBox(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        return cls(
            key=key,
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            box=box,
            label=str(data.get("label", "")),
            expected_keywords=list(data.get("expected_keywords", [])),
            verified_count=int(data.get("verified_count", 0)),
            last_verified=str(data.get("last_verified", "")),
        )


def _call_verify_roi_text(
    ocr: OCRService,
    image: np.ndarray,
    expected_keywords: List[str],
    center: Point,
    box: Optional[BoundingBox],
    roi_radius: float,
) -> bool:
    """Invokes OCRService.verify_roi_text adapting flexibly to whatever signature is implemented."""
    if not expected_keywords or image is None or ocr is None:
        return False

    if box is not None:
        roi = BoundingBox(
            x1=max(0.0, min(box.x1, center.x - roi_radius)),
            y1=max(0.0, min(box.y1, center.y - roi_radius)),
            x2=min(1.0, max(box.x2, center.x + roi_radius)),
            y2=min(1.0, max(box.y2, center.y + roi_radius)),
        )
    else:
        roi = BoundingBox(
            x1=max(0.0, center.x - roi_radius),
            y1=max(0.0, center.y - roi_radius),
            x2=min(1.0, center.x + roi_radius),
            y2=min(1.0, center.y + roi_radius),
        )

    # First attempt: signature (image, roi, expected_texts)
    try:
        return bool(ocr.verify_roi_text(image, roi, expected_keywords))
    except (TypeError, AttributeError):
        pass

    # Second attempt: signature (image, expected_keywords, center_norm, roi_radius_norm)
    try:
        return bool(ocr.verify_roi_text(image, expected_keywords, center, roi_radius_norm=roi_radius))
    except (TypeError, AttributeError):
        pass

    # Direct fallback if method signature is incompatible: crop directly and recognize
    try:
        h, w = image.shape[:2]
        x1 = max(0, int(roi.x1 * w))
        y1 = max(0, int(roi.y1 * h))
        x2 = min(w, int(roi.x2 * w))
        y2 = min(h, int(roi.y2 * h))
        if x2 > x1 and y2 > y1:
            crop = image[y1:y2, x1:x2]
            results = ocr.recognize(crop)
            norm_kw = [normalize_text(k) for k in expected_keywords]
            unacc_kw = [remove_vietnamese_tones(k) for k in norm_kw]
            for r in results:
                nr = normalize_text(r.text)
                ur = remove_vietnamese_tones(nr)
                for nk, uk in zip(norm_kw, unacc_kw):
                    if nk in nr or uk in ur or nr in nk or ur in uk:
                        return True
    except Exception as e:
        logger.debug(f"Direct crop OCR fallback failed: {e}")

    return False


class UICoordinateCache:
    """Manages persistent caching, micro-ROI verification, and self-healing for UI coordinates."""

    def __init__(self, filepath: str = CACHE_FILE):
        self.filepath = filepath
        self.metadata: Dict[str, Any] = {}
        self.elements: Dict[str, UIElement] = {}
        self.cache: Dict[str, dict] = {}
        self.load()

    def _sync_cache_dict(self) -> None:
        """Keeps self.cache dictionary in sync for backward compatibility."""
        self.cache = {k: elem.to_dict() for k, elem in self.elements.items()}

    def load(self) -> None:
        """Loads cached coordinates from JSON with fallback to defaults."""
        self.metadata = dict(DEFAULT_META)
        self.elements = {}

        # Populate baseline elements from defaults
        for k, d in DEFAULT_CACHE.items():
            self.elements[k] = UIElement.from_dict(k, d)

        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)

                if isinstance(loaded, dict):
                    # Check for modern schema with _meta and elements
                    if "_meta" in loaded and isinstance(loaded["_meta"], dict):
                        self.metadata.update(loaded["_meta"])

                    elements_data = loaded.get("elements", loaded)
                    if isinstance(elements_data, dict):
                        for k, d in elements_data.items():
                            if k == "_meta":
                                continue
                            if isinstance(d, dict):
                                self.elements[k] = UIElement.from_dict(k, d)

                logger.info(f"Đã nạp {len(self.elements)} vị trí nút bấm từ {self.filepath}")
            except Exception as e:
                logger.warning(f"Không thể đọc file cache {self.filepath}: {e}")
        else:
            self.save()

        self._sync_cache_dict()

    def save(self) -> None:
        """Persists current cache and metadata to disk."""
        try:
            self.metadata["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "_meta": self.metadata,
                "elements": {k: elem.to_dict() for k, elem in self.elements.items()},
            }
            tmp_file = f"{self.filepath}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, self.filepath)
            self._sync_cache_dict()
            logger.debug(f"Đã lưu {len(self.elements)} nút bấm vào {self.filepath}")
        except Exception as e:
            logger.error(f"Lỗi khi lưu cache {self.filepath}: {e}")

    def update_resolution(self, width: int, height: int) -> None:
        """Updates device resolution metadata and recalculates aspect ratio."""
        self.metadata["screen_width"] = int(width)
        self.metadata["screen_height"] = int(height)
        if width > 0 and height > 0:
            gcd = math.gcd(width, height)
            rw, rh = width // gcd, height // gcd
            self.metadata["aspect_ratio"] = f"{rw}:{rh}" if rw < 50 else f"{width}:{height}"
        self.save()

    def get_element(self, key: str) -> Optional[UIElement]:
        """Returns UIElement if key exists."""
        return self.elements.get(key)

    def get_point(self, key: str) -> Optional[Point]:
        """Returns normalized Point if key exists."""
        elem = self.elements.get(key)
        return elem.point if elem else None

    def get_box(self, key: str) -> Optional[BoundingBox]:
        """Returns normalized BoundingBox if key exists."""
        elem = self.elements.get(key)
        return elem.box if elem else None

    def update(
        self,
        key: str,
        x: float,
        y: float,
        box: Optional[BoundingBox] = None,
        label: str = "",
        keywords: Optional[List[str]] = None,
    ) -> None:
        """Updates an existing button coordinate or dynamically registers a new one."""
        existing = self.elements.get(key)
        if existing is not None:
            existing.x = round(float(x), 4)
            existing.y = round(float(y), 4)
            if box is not None:
                existing.box = box
            if label:
                existing.label = label
            if keywords is not None:
                existing.expected_keywords = list(keywords)
            existing.last_verified = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            self.elements[key] = UIElement(
                key=key,
                x=round(float(x), 4),
                y=round(float(y), 4),
                box=box,
                label=label or key,
                expected_keywords=list(keywords) if keywords else [],
                last_verified=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        self.save()
        logger.info(f"Đã cập nhật cache cho nút '{key}': ({x:.4f}, {y:.4f})")

    def verify_and_get(
        self,
        key: str,
        image: np.ndarray,
        ocr: OCRService,
        roi_radius: float = 0.05,
        auto_heal: bool = True,
    ) -> Tuple[Optional[Point], Optional[BoundingBox], bool]:
        """Verifies UI button location via fast-path micro-ROI with self-healing fallback.

        Returns:
            Tuple of (Point, BoundingBox, is_fast_path):
            - is_fast_path = True if verified in micro-ROI sub-window (< 60ms).
            - is_fast_path = False if healed/recovered via full-screen OCR.
            - (None, None, False) if element cannot be verified or found.
        """
        if image is None:
            return (None, None, False)

        elem = self.get_element(key)

        # 1. Fast-Path: localized Micro-ROI verification
        if elem is not None:
            if not elem.expected_keywords:
                # Pure icons without text keywords (e.g. phone_menu_icon, back_button)
                elem.verified_count += 1
                elem.last_verified = time.strftime("%Y-%m-%d %H:%M:%S")
                return (elem.point, elem.box, True)

            matched = _call_verify_roi_text(
                ocr=ocr,
                image=image,
                expected_keywords=elem.expected_keywords,
                center=elem.point,
                box=elem.box,
                roi_radius=roi_radius,
            )
            if matched:
                elem.verified_count += 1
                elem.last_verified = time.strftime("%Y-%m-%d %H:%M:%S")
                return (elem.point, elem.box, True)

        # 2. Fallback: Full-screen OCR when micro-ROI fails or element is missing
        if not auto_heal or ocr is None:
            return (None, None, False)

        keywords = elem.expected_keywords if elem and elem.expected_keywords else []
        if not keywords:
            return (None, None, False)

        h, w = image.shape[:2]
        if h == 0 or w == 0:
            return (None, None, False)

        all_results = ocr.recognize(image)
        if not all_results:
            return (None, None, False)

        matches = []
        for res in all_results:
            norm_res = normalize_text(res.text)
            unacc_res = remove_vietnamese_tones(norm_res)
            for kw in keywords:
                norm_kw = normalize_text(kw)
                unacc_kw = remove_vietnamese_tones(norm_kw)
                if norm_kw in norm_res or unacc_kw in unacc_res or norm_res in norm_kw or unacc_res in unacc_kw:
                    matches.append(res)
                    break

        if not matches:
            return (None, None, False)

        # Select closest match to previous coordinates if available, otherwise highest score
        if elem is not None:
            best_match = min(
                matches,
                key=lambda m: (m.center.x / w - elem.x) ** 2 + (m.center.y / h - elem.y) ** 2,
            )
        else:
            best_match = max(matches, key=lambda m: m.score)

        new_x = float(best_match.center.x / w)
        new_y = float(best_match.center.y / h)
        new_box = BoundingBox(
            x1=float(best_match.box.x1 / w),
            y1=float(best_match.box.y1 / h),
            x2=float(best_match.box.x2 / w),
            y2=float(best_match.box.y2 / h),
        )

        old_coords = f"({elem.x:.4f}, {elem.y:.4f})" if elem else "None"
        logger.warning(
            f"[Self-Healing] Nút '{key}' tự động cập nhật vị trí mới: ({new_x:.4f}, {new_y:.4f}) [Cũ: {old_coords}]"
        )

        self.update(
            key=key,
            x=new_x,
            y=new_y,
            box=new_box,
            label=elem.label if elem else key,
            keywords=keywords,
        )
        updated_elem = self.get_element(key)
        if updated_elem:
            updated_elem.verified_count += 1
            self.save()

        return (Point(new_x, new_y), new_box, False)


# Singleton instance
ui_cache = UICoordinateCache()
