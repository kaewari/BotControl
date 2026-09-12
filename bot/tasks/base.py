"""Base task class with lifecycle management, logging, and vision helpers."""
import time
import logging
from typing import Callable, List, Optional, Tuple
import numpy as np

from bot.core.coordinates import BoundingBox, Point, HSRZones
from bot.core.device import DeviceManager
from bot.cv.ocr_service import OCRService, OCRResult
from bot.cv.matcher import TemplateMatcher

logger = logging.getLogger("BotControl.Task")


class BaseTask:
    """Base class for all automation tasks."""

    def __init__(
        self,
        device: DeviceManager,
        ocr: Optional[OCRService] = None,
        matcher: Optional[TemplateMatcher] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.device = device
        self.ocr = ocr if ocr is not None else OCRService()
        self.matcher = matcher if matcher is not None else TemplateMatcher()
        self.log_callback = log_callback
        self.is_running = False
        self.stop_requested = False
        self.pause_requested = False
        self.task_name = self.__class__.__name__

    def log(self, message: str, level: str = "info"):
        """Logs message to console and dashboard websocket."""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{self.task_name}] {message}"
        if level == "error":
            logger.error(formatted)
        elif level == "warning":
            logger.warning(formatted)
        else:
            logger.info(formatted)

        if self.log_callback:
            try:
                self.log_callback(formatted, level)
            except Exception:
                pass

    def stop(self):
        """Requests task to gracefully stop."""
        self.stop_requested = True
        self.log("Đã gửi yêu cầu dừng tác vụ.", "warning")

    def pause(self):
        """Pauses task execution."""
        self.pause_requested = True
        self.log("Tác vụ đang tạm dừng.", "info")

    def resume(self):
        """Resumes paused task."""
        self.pause_requested = False
        self.log("Tiếp tục tác vụ.", "info")

    def sleep_cancellable(self, seconds: float, step: float = 0.1, jitter: bool = True) -> bool:
        """Sleeps in small increments with cognitive jitter, checking for stop/pause requests."""
        import random
        # Bổ sung timing jitter tự nhiên (±12% thời gian)
        if jitter and seconds > 0.3:
            actual_seconds = max(0.1, seconds + random.gauss(0, seconds * 0.12))
        else:
            actual_seconds = seconds

        elapsed = 0.0
        while elapsed < actual_seconds:
            if self.stop_requested:
                return False
            while self.pause_requested and not self.stop_requested:
                time.sleep(0.2)
            time.sleep(min(step, actual_seconds - elapsed))
            elapsed += step
        return not self.stop_requested

    def cognitive_pause(self, mean: float = 1.2, std: float = 0.35) -> bool:
        """Pauses execution to simulate a human reading the screen or thinking before clicking."""
        import random
        delay = max(0.4, min(3.5, random.gauss(mean, std)))
        self.log(f"Khoảng nghỉ suy nghĩ tự nhiên ({delay:.2f}s)...")
        return self.sleep_cancellable(delay, jitter=False)

    def check_threats(self, image: np.ndarray) -> bool:
        """Scans screen for Captchas or security checks, halting execution if detected."""
        from bot.core.human_touch import ThreatDetector
        if image is None:
            return False
        results = self.ocr.recognize(image)
        texts = [r.text for r in results]
        threat_detected, reason = ThreatDetector.check_for_threats(texts)
        if threat_detected:
            self.log(f"🚨 CẢNH BÁO NGUY CƠ: {reason}!", level="error")
            self.log("Lập tức kích hoạt Failsafe Kill-Switch ngắt toàn bộ thao tác!", level="error")
            self.stop_requested = True
            return True
        return False

    def capture(self) -> Optional[np.ndarray]:
        """Captures fresh screenshot from iPad."""
        return self.device.get_screenshot()

    def wait_for_text(
        self,
        target: str,
        timeout: float = 10.0,
        min_score: float = 0.5,
        region: Optional[BoundingBox] = None,
        check_interval: float = 0.6,
    ) -> Optional[OCRResult]:
        """Polls until specified text appears on screen or timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.stop_requested:
                return None
            img = self.capture()
            if img is not None:
                res = self.ocr.find_text(img, target, min_score=min_score, region=region)
                if res is not None:
                    return res
            if not self.sleep_cancellable(check_interval):
                return None
        return None

    def wait_for_any_text(
        self,
        targets: List[str],
        timeout: float = 10.0,
        min_score: float = 0.5,
        region: Optional[BoundingBox] = None,
        check_interval: float = 0.6,
    ) -> Optional[Tuple[str, OCRResult]]:
        """Polls until any specified text appears on screen or timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.stop_requested:
                return None
            img = self.capture()
            if img is not None:
                match = self.ocr.find_any_text(img, targets, min_score=min_score, region=region)
                if match is not None:
                    return match
            if not self.sleep_cancellable(check_interval):
                return None
        return None

    def tap_text(
        self,
        target: str,
        timeout: float = 5.0,
        region: Optional[BoundingBox] = None,
    ) -> bool:
        """Finds text and taps its center."""
        match = self.wait_for_text(target, timeout=timeout, region=region)
        if match is not None:
            # Match box coordinates are absolute pixels on image
            cx, cy = match.center.x, match.center.y
            self.device.tap(cx, cy, normalized=False)
            self.log(f"Đã tap vào chữ: '{match.text}' ({int(cx)}, {int(cy)})")
            return True
        return False

    def tap_zone(self, box: BoundingBox):
        """Taps normalized bounding box center."""
        self.device.tap_box(box, normalized=True)

    def run(self, **kwargs):
        """Main execution method to be overridden by subclasses."""
        raise NotImplementedError
