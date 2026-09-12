"""Device manager for iPad Pro M5 via WebDriverAgent."""
import io
import time
import logging
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image
import requests

from bot.core.coordinates import Point, BoundingBox, CoordinateSystem

logger = logging.getLogger("BotControl.Device")


class DeviceManager:
    """Manages WebDriverAgent connection, touch input, and screen streaming."""

    def __init__(self, wda_url: str = "http://localhost:8100", udid: Optional[str] = None):
        self.wda_url = wda_url.rstrip("/")
        self.udid = udid
        self._client = None
        self._session = None
        self.connected = False
        self.width = 2752
        self.height = 2064
        self.coords = CoordinateSystem(self.width, self.height)
        self.last_screenshot: Optional[np.ndarray] = None
        self.last_screenshot_bytes: Optional[bytes] = None
        self.last_screenshot_time: float = 0.0

    def connect(self) -> bool:
        """Connects to WebDriverAgent and retrieves device dimensions."""
        try:
            resp = requests.get(f"{self.wda_url}/status", timeout=2.0)
            if resp.status_code == 200:
                import wda
                self._client = wda.Client(self.wda_url)
                # Query window size
                window_size = self._client.window_size()
                self.width = int(window_size.width)
                self.height = int(window_size.height)
                self.coords.update_resolution(self.width, self.height)
                self.connected = True
                logger.info(f"Kết nối WDA thành công: iPad resolution {self.width}x{self.height}")
                return True
        except Exception as e:
            logger.warning(f"Chưa thể kết nối tới WDA tại {self.wda_url}: {e}")
            self.connected = False
        return False

    def check_connection(self) -> bool:
        """Lightweight check to see if WDA endpoint is alive."""
        try:
            resp = requests.get(f"{self.wda_url}/status", timeout=1.0)
            self.connected = (resp.status_code == 200)
        except Exception:
            self.connected = False
        return self.connected

    def get_screenshot(self) -> Optional[np.ndarray]:
        """Captures a screenshot from iPad as BGR numpy array."""
        if not self.connected:
            if not self.connect():
                return None

        try:
            # First attempt: standard WDA screenshot endpoint
            resp = requests.get(f"{self.wda_url}/screenshot", timeout=3.0)
            if resp.status_code == 200:
                img_bytes = resp.content
                self.last_screenshot_bytes = img_bytes
                self.last_screenshot_time = time.time()
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    # Update dimensions if changed
                    h, w = img.shape[:2]
                    if w != self.width or h != self.height:
                        self.width = w
                        self.height = h
                        self.coords.update_resolution(w, h)
                    self.last_screenshot = img
                    return img
        except Exception as e:
            logger.error(f"Lỗi chụp ảnh màn hình từ WDA: {e}")
            self.connected = False
        return None

    def get_screenshot_jpeg_bytes(self) -> Optional[bytes]:
        """Returns JPEG bytes directly for live video streaming."""
        img = self.get_screenshot()
        if img is not None:
            ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                return buf.tobytes()
        return self.last_screenshot_bytes

    def tap(self, x: float, y: float, normalized: bool = True):
        """Taps at coordinate. If normalized=True, x,y are in [0.0 - 1.0]."""
        if not self.connected and not self.connect():
            logger.warning("Không thể gửi tap: WDA chưa kết nối")
            return

        if normalized:
            abs_x = int(round(x * self.width))
            abs_y = int(round(y * self.height))
        else:
            abs_x = int(round(x))
            abs_y = int(round(y))

        logger.debug(f"Tap tại ({abs_x}, {abs_y}) [norm: {x:.3f}, {y:.3f}]")
        try:
            # Call WDA tap API directly
            payload = {"x": abs_x, "y": abs_y}
            requests.post(f"{self.wda_url}/wda/tap/nil", json=payload, timeout=2.0)
        except Exception as e:
            logger.error(f"Lỗi gửi tap: {e}")

    def tap_box(self, box: BoundingBox, normalized: bool = True):
        """Taps the center of a bounding box."""
        center = box.center
        self.tap(center.x, center.y, normalized=normalized)

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5, normalized: bool = True):
        """Performs a swipe gesture between two points."""
        if not self.connected and not self.connect():
            return

        if normalized:
            from_x = int(round(x1 * self.width))
            from_y = int(round(y1 * self.height))
            to_x = int(round(x2 * self.width))
            to_y = int(round(y2 * self.height))
        else:
            from_x, from_y, to_x, to_y = int(x1), int(y1), int(x2), int(y2)

        try:
            payload = {
                "fromX": from_x,
                "fromY": from_y,
                "toX": to_x,
                "toY": to_y,
                "duration": duration,
            }
            requests.post(f"{self.wda_url}/wda/dragfromtoforduration", json=payload, timeout=duration + 2.0)
        except Exception as e:
            logger.error(f"Lỗi gửi swipe: {e}")
