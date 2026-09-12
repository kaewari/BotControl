"""RapidOCR service with Vietnamese text normalization and fuzzy matching."""
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
    # NFKC normalizes unicode characters
    text = unicodedata.normalize("NFKC", text).strip().lower()
    # Replace multiple whitespaces with single space
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
                # item format: [box_points, text, score]
                # box_points is [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
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
