"""OpenCV Template Matching with multi-scale matching and confidence scoring."""
import os
import logging
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np

from bot.core.coordinates import BoundingBox, Point

logger = logging.getLogger("BotControl.Matcher")


class TemplateMatcher:
    """Manages template loading and matching on game screenshots."""

    def __init__(self, templates_dir: Optional[str] = None):
        self.templates_dir = templates_dir or os.path.join(os.path.dirname(__file__), "templates")
        self.templates: Dict[str, np.ndarray] = {}
        self._load_templates()

    def _load_templates(self):
        """Loads all .png and .jpg templates from templates directory."""
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir, exist_ok=True)
            return

        for fname in os.listdir(self.templates_dir):
            if fname.lower().endswith((".png", ".jpg", ".jpeg")):
                tpath = os.path.join(self.templates_dir, fname)
                img = cv2.imread(tpath, cv2.IMREAD_COLOR)
                if img is not None:
                    name = os.path.splitext(fname)[0]
                    self.templates[name] = img
                    logger.debug(f"Đã load template: {name} ({img.shape[1]}x{img.shape[0]})")

    def register_template(self, name: str, image: np.ndarray):
        """Registers a new template dynamically."""
        self.templates[name] = image

    def match(
        self,
        image: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[BoundingBox] = None,
        scales: Tuple[float, ...] = (1.0, 0.9, 1.1),
    ) -> Optional[Tuple[BoundingBox, float]]:
        """Matches a registered template against an image across multiple scales."""
        template = self.templates.get(template_name)
        if template is None:
            logger.debug(f"Template '{template_name}' chưa được đăng ký")
            return None

        if image is None or image.size == 0:
            return None

        h, w = image.shape[:2]
        offset_x, offset_y = 0, 0

        if region is not None:
            x1 = max(0, int(region.x1))
            y1 = max(0, int(region.y1))
            x2 = min(w, int(region.x2))
            y2 = min(h, int(region.y2))
            if x2 > x1 and y2 > y1:
                image = image[y1:y2, x1:x2]
                offset_x, offset_y = x1, y1

        th, tw = template.shape[:2]
        best_score = -1.0
        best_box = None

        img_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template

        for scale in scales:
            scaled_tw = int(tw * scale)
            scaled_th = int(th * scale)
            if scaled_tw >= img_gray.shape[1] or scaled_th >= img_gray.shape[0] or scaled_tw <= 4 or scaled_th <= 4:
                continue

            scaled_tpl = cv2.resize(tpl_gray, (scaled_tw, scaled_th), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(img_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val > best_score:
                best_score = max_val
                best_box = BoundingBox(
                    x1=float(max_loc[0] + offset_x),
                    y1=float(max_loc[1] + offset_y),
                    x2=float(max_loc[0] + offset_x + scaled_tw),
                    y2=float(max_loc[1] + offset_y + scaled_th),
                )

        if best_score >= threshold and best_box is not None:
            return (best_box, best_score)

        return None
