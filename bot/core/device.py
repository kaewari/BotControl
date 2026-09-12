"""Device manager for iPad Pro M5 via WebDriverAgent."""
import io
import time
import logging
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import wda

from bot.core.coordinates import CoordinateSystem, Point, BoundingBox
from bot.core.human_touch import (
    generate_gaussian_point,
    generate_bezier_trajectory,
    random_touch_duration,
)

logger = logging.getLogger("BotControl.Device")


class DeviceManager:
    """Manages iPad device connection via WebDriverAgent and screen interactions."""

    def __init__(self, wda_url: str = "http://127.0.0.1:8100", timeout: float = 30.0):
        self.wda_url = wda_url
        self.timeout = timeout
        self.connected = False
        self._client: Optional[wda.Client] = None
        self.pixel_width = 2752
        self.pixel_height = 2064
        self.coords = CoordinateSystem(self.pixel_width, self.pixel_height)
        self.last_screenshot = None
        self.last_screenshot_time = 0.0
        self.last_screenshot_bytes = None
        self.enable_human_touch = True

    @property
    def width(self) -> int:
        return self.pixel_width

    @property
    def height(self) -> int:
        return self.pixel_height

    def connect(self) -> bool:
        """Connects to WebDriverAgent and retrieves device dimensions."""
        try:
            self._client = wda.Client(self.wda_url)
            status = self._client.status()
            if status.get("state") == "success" or "ready" in str(status):
                self.connected = True
                logger.info(f"Kết nối WDA thành công: {self.wda_url}")
                return True
        except Exception as e:
            logger.debug(f"Chưa kết nối được WDA tại {self.wda_url}: {e}")
            self.connected = False
        return False

    def check_connection(self) -> bool:
        """Lightweight check to see if WDA endpoint is alive."""
        if self._client is None:
            return self.connect()
        try:
            status = self._client.status()
            self.connected = (status.get("state") == "success" or "ready" in str(status))
        except Exception:
            self.connected = False
            self._client = None
        return self.connected

    def get_screenshot(self) -> Optional[np.ndarray]:
        """Captures a screenshot from iPad as BGR numpy array."""
        if not self.connected:
            if not self.connect():
                return None

        try:
            pil_img = self._client.screenshot()
            if pil_img is not None:
                pw, ph = pil_img.size
                if pw != self.pixel_width or ph != self.pixel_height:
                    self.pixel_width = pw
                    self.pixel_height = ph
                    self.coords.update_resolution(pw, ph)

                rgb_arr = np.array(pil_img)
                bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
                self.last_screenshot = bgr_arr
                self.last_screenshot_time = time.time()
                return bgr_arr
        except Exception as e:
            logger.error(f"Lỗi chụp ảnh màn hình từ WDA: {e}")
            self.connected = False
        return None

    def get_screenshot_jpeg_bytes(self) -> Optional[bytes]:
        """Returns JPEG bytes directly for live video streaming."""
        img = self.get_screenshot()
        if img is not None:
            small = cv2.resize(img, (1024, 768), interpolation=cv2.INTER_AREA)
            ret, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                self.last_screenshot_bytes = buf.tobytes()
                return self.last_screenshot_bytes
        return self.last_screenshot_bytes

    def tap(self, x: float, y: float, normalized: bool = True, box: Optional[BoundingBox] = None):
        """Taps at coordinate with optional 2D Gaussian human dispersion and biological contact duration."""
        if not self.connected and not self.connect():
            logger.warning("Không thể gửi tap: WDA chưa kết nối")
            return

        if normalized:
            norm_x = float(max(0.0, min(1.0, x)))
            norm_y = float(max(0.0, min(1.0, y)))
        else:
            norm_x = float(max(0.0, min(1.0, x / self.pixel_width)))
            norm_y = float(max(0.0, min(1.0, y / self.pixel_height)))

        # Áp dụng mô phỏng chạm người thật (Human-like touch)
        if self.enable_human_touch:
            hp = generate_gaussian_point(Point(norm_x, norm_y), box=box)
            norm_x = float(max(0.005, min(0.995, hp.x)))
            norm_y = float(max(0.005, min(0.995, hp.y)))
            hold_dur = random_touch_duration()
        else:
            hold_dur = 0.0

        logger.info(f"Thực hiện chạm tại ({norm_x:.4f}, {norm_y:.4f}) [giữ {hold_dur*1000:.0f}ms]")
        try:
            if hold_dur > 0.05:
                self._client.tap_hold(norm_x, norm_y, duration=hold_dur)
            else:
                self._client.click(norm_x, norm_y)
        except Exception as e:
            logger.error(f"Lỗi gửi tap: {e}")

    def tap_box(self, box, normalized: bool = True):
        """Taps inside a bounding box using 2D Gaussian distribution, or point."""
        if isinstance(box, BoundingBox):
            self.tap(box.center.x, box.center.y, normalized=normalized, box=box)
        elif hasattr(box, "center"):
            self.tap(box.center.x, box.center.y, normalized=normalized)
        elif hasattr(box, "x") and hasattr(box, "y"):
            self.tap(box.x, box.y, normalized=normalized)

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5, normalized: bool = True):
        """Performs a humanized swipe gesture between two points."""
        if not self.connected and not self.connect():
            return

        if normalized:
            nx1, ny1, nx2, ny2 = x1, y1, x2, y2
        else:
            nx1 = x1 / self.pixel_width
            ny1 = y1 / self.pixel_height
            nx2 = x2 / self.pixel_width
            ny2 = y2 / self.pixel_height

        # Bổ sung jitter thời gian và vị trí điểm vuốt
        if self.enable_human_touch:
            import random
            duration = duration * random.uniform(0.92, 1.15)
            sp = generate_gaussian_point(Point(nx1, ny1))
            ep = generate_gaussian_point(Point(nx2, ny2))
            nx1, ny1, nx2, ny2 = sp.x, sp.y, ep.x, ep.y

        try:
            self._client.swipe(float(nx1), float(ny1), float(nx2), float(ny2), duration=duration)
        except Exception as e:
            logger.error(f"Lỗi gửi swipe: {e}")
