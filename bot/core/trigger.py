"""Event-driven Screen State Trigger and Fast Chain Executor for BotControl.

Provides:
- FreshFrameGuard: ensures actions evaluate only frames captured after the trigger was armed.
- ScreenStateTrigger: micro-polling loop (< 40ms) evaluating screen conditions and Micro-ROI text.
- FastChainExecutor: executes sequential taps with biological hold and Gaussian cadence.
"""
import time
import random
from typing import Any, Callable, List, Optional, Tuple
import cv2
import numpy as np

from bot.core.coordinates import Point, BoundingBox


class FreshFrameGuard:
    """Timestamp guard ensuring pre-action cached frames are discarded."""

    def __init__(self, action_timestamp: float):
        self.action_timestamp = action_timestamp

    def is_fresh(self, frame_timestamp: float) -> bool:
        return frame_timestamp > self.action_timestamp


class ScreenStateTrigger:
    """Event-driven screen state trigger replacing static time.sleep with reactive polling."""

    def __init__(self, device: Any, ocr: Any = None):
        self.device = device
        self.ocr = ocr
        self._last_action_time = 0.0

    def record_action(self):
        self._last_action_time = time.time()

    def wait_for_condition(
        self,
        predicate: Callable[[np.ndarray], bool],
        timeout: float = 5.0,
        poll_interval: float = 0.04,
        min_delay: float = 0.08,
    ) -> bool:
        """Micro-polling condition wait loop."""
        start = time.time()
        if min_delay > 0:
            time.sleep(min_delay)

        while time.time() - start < timeout:
            img = self.device.get_screenshot()
            if img is not None:
                vframe = getattr(self.device, "get_video_frame", lambda: None)()
                if vframe is not None and self._last_action_time > 0:
                    if vframe.timestamp <= self._last_action_time:
                        time.sleep(poll_interval)
                        continue

                try:
                    if predicate(img):
                        return True
                except Exception:
                    pass
            time.sleep(poll_interval)
        return False

    def wait_for_roi_text(
        self,
        keywords: List[str],
        center_norm: Point,
        timeout: float = 4.0,
        roi_radius: float = 0.06,
        poll_interval: float = 0.04,
    ) -> bool:
        """Micro-ROI localized sub-window text trigger."""
        box = BoundingBox(
            max(0.0, center_norm.x - roi_radius),
            max(0.0, center_norm.y - roi_radius),
            min(1.0, center_norm.x + roi_radius),
            min(1.0, center_norm.y + roi_radius),
        )

        def check_roi(img: np.ndarray) -> bool:
            if self.ocr is None:
                return False
            if hasattr(self.ocr, "verify_roi_text"):
                return bool(self.ocr.verify_roi_text(img, box, keywords))
            return False

        return self.wait_for_condition(check_roi, timeout=timeout, poll_interval=poll_interval)

    def wait_for_screen_stable(
        self,
        region: Optional[BoundingBox] = None,
        max_change_ratio: float = 0.005,
        timeout: float = 3.0,
        stable_frames: int = 2,
        poll_interval: float = 0.04,
    ) -> bool:
        """Detects screen stabilization via pixel absdiff ratio <= max_change_ratio."""
        start = time.time()
        prev_crop: Optional[np.ndarray] = None
        consecutive_stable = 0

        while time.time() - start < timeout:
            img = self.device.get_screenshot()
            if img is None:
                time.sleep(poll_interval)
                continue

            h, w = img.shape[:2]
            if region is not None:
                x1, y1 = max(0, int(region.x1 * w)), max(0, int(region.y1 * h))
                x2, y2 = min(w, int(region.x2 * w)), min(h, int(region.y2 * h))
                crop = img[y1:y2, x1:x2]
            else:
                crop = img

            if crop.size == 0:
                time.sleep(poll_interval)
                continue

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop

            if prev_crop is not None and prev_crop.shape == gray.shape:
                diff = cv2.absdiff(prev_crop, gray)
                changed_pixels = np.count_nonzero(diff > 15)
                ratio = changed_pixels / float(gray.size)

                if ratio <= max_change_ratio:
                    consecutive_stable += 1
                    if consecutive_stable >= stable_frames:
                        return True
                else:
                    consecutive_stable = 0

            prev_crop = gray
            time.sleep(poll_interval)

        return False


class FastChainExecutor:
    """Executes fast action chains with biological touch hold and Gaussian cadence."""

    def __init__(self, device: Any, stop_predicate: Optional[Callable[[], bool]] = None):
        self.device = device
        self.stop_predicate = stop_predicate or (lambda: False)

    def execute_chain(
        self,
        targets: List[Tuple[Point, Optional[BoundingBox]]],
        mean_cadence: float = 0.145,
        std_cadence: float = 0.022,
    ) -> bool:
        """Executes sequential actions with Gaussian cadence and biological touch hold."""
        if not targets:
            return True

        for i, (point, box) in enumerate(targets):
            if self.stop_predicate():
                return False

            if box is not None:
                self.device.tap(point.x, point.y, normalized=True, box=box)
            else:
                self.device.tap(point.x, point.y, normalized=True)

            if i < len(targets) - 1:
                cadence = random.gauss(mean_cadence, std_cadence)
                clamped_cadence = max(0.105, min(0.200, cadence))
                time.sleep(clamped_cadence)

        return True
