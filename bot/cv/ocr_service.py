"""RapidOCR service with Vietnamese text normalization, fuzzy matching, and HSR data extraction."""
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from bot.core.coordinates import BoundingBox, Point

logger = logging.getLogger("BotControl.OCR")


def normalize_text(text: str) -> str:
    """Normalize text: strip, lowercase, convert to standard unicode form."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def remove_vietnamese_tones(text: str) -> str:
    """Strip Vietnamese accent marks for tolerant matching."""
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = text.replace("đ", "d").replace("Đ", "D")
    return text


@dataclass
class OCRResult:
    text: str
    score: float
    box: BoundingBox  # Absolute pixel coordinates (x1, y1, x2, y2)

    @property
    def center(self) -> Point:
        return self.box.center


class OCRService:
    """Provides high-performance OCR recognition and text location."""

    def __init__(self):
        logger.info("Khởi tạo RapidOCR engine...")
        self.engine = RapidOCR()

    def recognize(self, image: np.ndarray, region: Optional[BoundingBox] = None) -> List[OCRResult]:
        """Runs OCR on image (or cropped region) and returns recognized text items with boxes."""
        if image is None or image.size == 0:
            return []

        h, w = image.shape[:2]
        offset_x, offset_y = 0, 0

        # Crop if sub-region specified
        if region is not None:
            x1 = max(0, int(region.x1))
            y1 = max(0, int(region.y1))
            x2 = min(w, int(region.x2))
            y2 = min(h, int(region.y2))
            if x2 > x1 and y2 > y1:
                image = image[y1:y2, x1:x2]
                offset_x, offset_y = x1, y1

        try:
            results, elapse_list = self.engine(image)
            if not results:
                return []

            parsed_results: List[OCRResult] = []
            for item in results:
                box_pts = item[0]
                text = str(item[1]).strip()
                score = float(item[2])

                pts_x = [pt[0] + offset_x for pt in box_pts]
                pts_y = [pt[1] + offset_y for pt in box_pts]

                b_box = BoundingBox(
                    x1=float(min(pts_x)),
                    y1=float(min(pts_y)),
                    x2=float(max(pts_x)),
                    y2=float(max(pts_y)),
                )
                parsed_results.append(OCRResult(text=text, score=score, box=b_box))
            return parsed_results
        except Exception as e:
            logger.error(f"Lỗi chạy RapidOCR: {e}")
            return []

    def find_text(
        self,
        image: np.ndarray,
        target: str,
        min_score: float = 0.5,
        region: Optional[BoundingBox] = None,
        ignore_tones: bool = True,
    ) -> Optional[OCRResult]:
        """Finds first matching text entry in image."""
        results = self.recognize(image, region=region)
        norm_target = normalize_text(target)
        unaccented_target = remove_vietnamese_tones(norm_target) if ignore_tones else ""

        for res in results:
            if res.score < min_score:
                continue

            norm_res_text = normalize_text(res.text)
            if norm_target in norm_res_text:
                return res

            if ignore_tones:
                unaccented_res = remove_vietnamese_tones(norm_res_text)
                if unaccented_target in unaccented_res:
                    return res

        return None

    def find_all_text(
        self,
        image: np.ndarray,
        target: str,
        min_score: float = 0.5,
        region: Optional[BoundingBox] = None,
        ignore_tones: bool = True,
    ) -> List[OCRResult]:
        """Finds all matching text entries in image."""
        results = self.recognize(image, region=region)
        norm_target = normalize_text(target)
        unaccented_target = remove_vietnamese_tones(norm_target) if ignore_tones else ""
        matches = []
        for res in results:
            if res.score < min_score:
                continue
            norm_res_text = normalize_text(res.text)
            if norm_target in norm_res_text:
                matches.append(res)
            elif ignore_tones:
                unaccented_res = remove_vietnamese_tones(norm_res_text)
                if unaccented_target in unaccented_res:
                    matches.append(res)
        return matches

    def verify_roi_text(
        self,
        image: np.ndarray,
        expected_keywords: List[str],
        center_norm: Point,
        roi_radius_norm: float = 0.08,
    ) -> bool:
        """Fast Micro-ROI check: crops only a small sub-window around the cached point.
        Runs in ~20-30ms compared to ~2000ms for full-screen OCR.
        """
        if image is None:
            return False
        h, w = image.shape[:2]
        cx, cy = center_norm.x * w, center_norm.y * h
        rw, rh = roi_radius_norm * w, roi_radius_norm * h

        x1 = max(0, int(cx - rw))
        y1 = max(0, int(cy - rh))
        x2 = min(w, int(cx + rw))
        y2 = min(h, int(cy + rh))

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return False

        results = self.recognize(crop)
        crop_texts = [normalize_text(r.text) for r in results]
        crop_unaccented = [remove_vietnamese_tones(t) for t in crop_texts]

        for kw in expected_keywords:
            norm_kw = normalize_text(kw)
            unaccented_kw = remove_vietnamese_tones(norm_kw)
            for t, u in zip(crop_texts, crop_unaccented):
                if norm_kw in t or unaccented_kw in u:
                    return True
        return False

    def find_any_text(
        self,
        image: np.ndarray,
        targets: List[str],
        min_score: float = 0.5,
        region: Optional[BoundingBox] = None,
    ) -> Optional[Tuple[str, OCRResult]]:
        """Finds any matching text from target list."""
        for target in targets:
            match = self.find_text(image, target, min_score=min_score, region=region)
            if match is not None:
                return (target, match)
        return None

    def extract_trailblaze_power(self, image: np.ndarray) -> Optional[Tuple[int, int]]:
        """Extracts current and max Trailblaze Power from top bar (e.g. 164/300)."""
        if image is None:
            return None
        h, w = image.shape[:2]
        # Crop top region: x in [0.60, 0.95], y in [0.0, 0.15]
        top_bar = BoundingBox(w * 0.60, 0, w * 0.95, h * 0.15)
        results = self.recognize(image, region=top_bar)
        for r in results:
            # Pattern like 164/300 or 164/300+
            m = re.search(r"(\d{1,3})\s*/\s*(\d{3})", r.text)
            if m:
                try:
                    current = int(m.group(1))
                    maximum = int(m.group(2))
                    return (current, maximum)
                except ValueError:
                    pass
        return None

    def extract_fuel_count(self, image: np.ndarray) -> Optional[int]:
        """Extracts fuel count from top bar (e.g. 11)."""
        if image is None:
            return None
        h, w = image.shape[:2]
        fuel_region = BoundingBox(w * 0.55, 0, w * 0.75, h * 0.15)
        results = self.recognize(image, region=fuel_region)
        for r in results:
            if r.text.isdigit():
                return int(r.text)
        return None

    def find_action_button_on_row(
        self,
        image: np.ndarray,
        target_name: str,
        button_labels: List[str] = ["Vào", "Vao", "Khiêu Chiến", "Dịch Chuyển"],
        tolerance_y: float = 180.0,
    ) -> Optional[OCRResult]:
        """Finds a target label on the screen and returns the action button on the same horizontal row."""
        if image is None:
            return None

        h, w = image.shape[:2]
        eff_tolerance = max(tolerance_y, h * 0.09)
        results = self.recognize(image)
        norm_target = normalize_text(target_name)
        unaccented_target = remove_vietnamese_tones(norm_target)

        target_y: Optional[float] = None

        # 1. Locate target row
        for r in results:
            norm_r = normalize_text(r.text)
            unaccented_r = remove_vietnamese_tones(norm_r)
            if norm_target in norm_r or unaccented_target in unaccented_r:
                target_y = r.center.y
                break

        if target_y is None:
            return None

        # 2. Find button on the right side of that row (x > w * 0.7)
        h, w = image.shape[:2]
        best_btn = None
        min_dy = float("inf")

        for r in results:
            if r.center.x > w * 0.70:
                norm_r = normalize_text(r.text)
                for btn_lbl in button_labels:
                    if normalize_text(btn_lbl) in norm_r or remove_vietnamese_tones(btn_lbl) in remove_vietnamese_tones(norm_r):
                        dy = abs(r.center.y - target_y)
                        if dy <= tolerance_y and dy < min_dy:
                            min_dy = dy
                            best_btn = r

        return best_btn
