"""Mock WDA and Device Harness for non-intrusive unit and integration testing.

Prevents hardware leakage to live physical iPad Pro (port 8100) during test runs.
Provides synthetic frame generation, tap/swipe event recording, and mock implementations
of WDA Client, VideoFrame, ScreenStateTrigger, and FastChainExecutor.
"""
import io
import time
import base64
import random
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any, Callable
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from bot.core.coordinates import Point, BoundingBox, CoordinateSystem
from bot.core.human_touch import (
    generate_gaussian_point,
    random_touch_duration,
    generate_bezier_trajectory,
)

# VideoFrame definition matching PROJECT.md interface contract
@dataclass(frozen=True)
class VideoFrame:
    frame_id: int
    timestamp: float
    bgr: np.ndarray
    jpeg_bytes: bytes
    width: int
    height: int


class MockWDAHttp:
    """Simulates WDA HTTP client responses."""

    def __init__(self, client: "MockWDAClient"):
        self.client = client

    def get(self, endpoint: str):
        if endpoint == "screenshot":
            # Return base64 encoded PNG
            buf = io.BytesIO()
            self.client.current_pil_image.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return type("WDAVal", (), {"value": b64})()
        elif endpoint == "status":
            return type("WDAVal", (), {
                "value": {
                    "state": "success",
                    "sessionId": self.client.session_id,
                    "os": {"version": "26.6", "name": "iPadOS"},
                    "ready": True,
                }
            })()
        return type("WDAVal", (), {"value": {}})()

    def post(self, endpoint: str, data: Optional[dict] = None):
        return type("WDAVal", (), {"value": {}})()


class MockWDAClient:
    """Mock implementation of facebook-wda Client.

    Generates synthetic frames ($2752 x 2064$ by default) and intercepts
    all tap, tap_hold, and swipe calls without touching physical hardware.
    """

    def __init__(self, url: str = "http://127.0.0.1:8100"):
        self.url = url
        self.session_id = "mock-session-ipad-pro-m5"
        self.http = MockWDAHttp(self)
        self.width = 2752
        self.height = 2064
        self.taps: List[Dict[str, Any]] = []
        self.swipes: List[Dict[str, Any]] = []

        # Synthetic screen canvas
        self._current_image: Optional[Image.Image] = None
        self._reset_synthetic_canvas()

    def _reset_synthetic_canvas(self):
        img = Image.new("RGB", (self.width, self.height), color=(20, 24, 35))
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), "BotControl Mock Screen - iPad Pro 13 (M5)", fill=(255, 255, 255))
        self._current_image = img

    @property
    def current_pil_image(self) -> Image.Image:
        if self._current_image is None:
            self._reset_synthetic_canvas()
        return self._current_image

    def status(self) -> Dict[str, Any]:
        return {
            "state": "success",
            "sessionId": self.session_id,
            "value": {"state": "success", "ready": True},
            "ready": True,
        }

    def screenshot(self) -> Image.Image:
        return self.current_pil_image.copy()

    def set_screen_image(self, img: Image.Image):
        self._current_image = img

    def set_screen_bgr(self, bgr: np.ndarray):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self._current_image = Image.fromarray(rgb)

    def draw_button(self, box: BoundingBox, text: str, normalized: bool = True):
        """Draws a synthetic button onto the mock screen with text."""
        img = self.current_pil_image.copy()
        draw = ImageDraw.Draw(img)
        w, h = self.width, self.height
        if normalized:
            x1, y1 = int(box.x1 * w), int(box.y1 * h)
            x2, y2 = int(box.x2 * w), int(box.y2 * h)
        else:
            x1, y1 = int(box.x1), int(box.y1)
            x2, y2 = int(box.x2), int(box.y2)

        draw.rectangle([x1, y1, x2, y2], fill=(50, 70, 100), outline=(200, 200, 255), width=3)
        draw.text((x1 + 10, y1 + (y2 - y1) // 3), text, fill=(255, 255, 255))
        self._current_image = img

    def click(self, x: float, y: float):
        self.taps.append({
            "type": "click",
            "x": float(x),
            "y": float(y),
            "duration": 0.0,
            "timestamp": time.time(),
        })

    def tap_hold(self, x: float, y: float, duration: float = 0.1):
        self.taps.append({
            "type": "tap_hold",
            "x": float(x),
            "y": float(y),
            "duration": float(duration),
            "timestamp": time.time(),
        })

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5):
        self.swipes.append({
            "type": "swipe",
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
            "duration": float(duration),
            "timestamp": time.time(),
        })

    def clear_history(self):
        self.taps.clear()
        self.swipes.clear()


class MockDeviceManager:
    """Mock DeviceManager offering RAM double-buffering and tap tracking.

    Can be injected directly into BaseTask, DailyTask, and FastAPI web server
    to eliminate all hardware interactions.
    """

    def __init__(self, width: int = 2752, height: int = 2064):
        self.wda_url = "http://mock-wda:8100"
        self.connected = True
        self.pixel_width = width
        self.pixel_height = height
        self.coords = CoordinateSystem(width, height)
        self.enable_human_touch = True

        self._client = MockWDAClient(self.wda_url)
        self.tap_history: List[Dict[str, Any]] = []
        self.swipe_history: List[Dict[str, Any]] = []
        self.resource_guard: Optional[Any] = None

        # RAM Double Buffering
        self._frame_lock = threading.Lock()
        self._frame_counter = 0
        self._front_frame: Optional[VideoFrame] = None
        self._cached_bgr: Optional[np.ndarray] = None
        self._cached_jpeg: Optional[bytes] = None
        self._cached_time: float = 0.0
        self.last_screenshot: Optional[np.ndarray] = None
        self.last_screenshot_time: float = 0.0
        self.last_screenshot_bytes: Optional[bytes] = None

        # Producer thread simulation
        self._producer_running = False
        self._producer_thread: Optional[threading.Thread] = None

        # Initialize with an initial test frame
        self._init_default_frame()

    def _init_default_frame(self):
        bgr = np.zeros((self.pixel_height, self.pixel_width, 3), dtype=np.uint8)
        bgr[:] = (35, 24, 20)  # BGR dark navy
        cv2.putText(bgr, "BotControl Mock Frame", (150, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)
        self.set_frame(bgr)

    @property
    def width(self) -> int:
        return self.pixel_width

    @property
    def height(self) -> int:
        return self.pixel_height

    @property
    def resolution(self):
        class Res:
            width = self.pixel_width
            height = self.pixel_height
        return Res()

    def connect(self) -> bool:
        self.connected = True
        return True

    def check_connection(self) -> bool:
        return self.connected

    def set_frame(self, bgr: np.ndarray, timestamp: Optional[float] = None):
        """Atomically updates the front frame in RAM."""
        now = timestamp if timestamp is not None else time.time()
        self._frame_counter += 1

        # Render 960x720 JPEG
        small = cv2.resize(bgr, (960, 720), interpolation=cv2.INTER_AREA)
        ret, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 72])
        jpeg_bytes = buf.tobytes() if ret else b""

        new_frame = VideoFrame(
            frame_id=self._frame_counter,
            timestamp=now,
            bgr=bgr,
            jpeg_bytes=jpeg_bytes,
            width=self.pixel_width,
            height=self.pixel_height,
        )

        with self._frame_lock:
            self._front_frame = new_frame
            self._cached_bgr = bgr
            self._cached_jpeg = jpeg_bytes
            self._cached_time = now
            self.last_screenshot = bgr
            self.last_screenshot_time = now
            self.last_screenshot_bytes = jpeg_bytes

        self._client.set_screen_bgr(bgr)

    def get_video_frame(self) -> Optional[VideoFrame]:
        """0.0ms lock-free reader under Python GIL."""
        return self._front_frame

    def get_screenshot(self, force_fresh: bool = False, max_age: float = 0.20) -> Optional[np.ndarray]:
        now = time.time()
        if not force_fresh and self._cached_bgr is not None and (now - self._cached_time) < max_age:
            return self._cached_bgr.copy()
        if self._cached_bgr is not None:
            return self._cached_bgr.copy()
        return None

    def get_screenshot_jpeg_bytes(self) -> Optional[bytes]:
        if self._cached_jpeg is not None:
            return self._cached_jpeg
        return self.last_screenshot_bytes

    def tap(self, x: float, y: float, normalized: bool = True, box: Optional[BoundingBox] = None, label: str = ""):
        if normalized:
            norm_x = float(max(0.0, min(1.0, x)))
            norm_y = float(max(0.0, min(1.0, y)))
        else:
            norm_x = float(max(0.0, min(1.0, x / self.pixel_width)))
            norm_y = float(max(0.0, min(1.0, y / self.pixel_height)))

        # ResourceGuard pre-tap veto check
        if self.resource_guard is not None:
            target_label = label or getattr(box, "label", "")
            if self.resource_guard.is_vetoed_tap(norm_x, norm_y, label=target_label):
                import logging
                logging.getLogger("BotControl.MockDevice").critical(
                    f"🚫 [MOCK VETO STRICT] Thao tác tap tại ({norm_x:.4f}, {norm_y:.4f}) với nhãn '{target_label}' bị chặn bởi ResourceGuard!"
                )
                return

        if self.enable_human_touch:
            hp = generate_gaussian_point(Point(norm_x, norm_y), box=box)
            norm_x = float(max(0.005, min(0.995, hp.x)))
            norm_y = float(max(0.005, min(0.995, hp.y)))
            hold_dur = random_touch_duration()
        else:
            hold_dur = 0.0

        event = {
            "type": "tap_hold" if hold_dur > 0.05 else "click",
            "x": norm_x,
            "y": norm_y,
            "duration": hold_dur,
            "box": box,
            "label": label,
            "timestamp": time.time(),
        }
        self.tap_history.append(event)
        if hold_dur > 0.05:
            self._client.tap_hold(norm_x, norm_y, duration=hold_dur)
        else:
            self._client.click(norm_x, norm_y)

    def tap_box(self, box, normalized: bool = True):
        if isinstance(box, BoundingBox):
            self.tap(box.center.x, box.center.y, normalized=normalized, box=box)
        elif hasattr(box, "center"):
            self.tap(box.center.x, box.center.y, normalized=normalized)
        elif hasattr(box, "x") and hasattr(box, "y"):
            self.tap(box.x, box.y, normalized=normalized)

    def tap_hold(self, x: float, y: float, duration: float = 0.1, normalized: bool = True, box: Optional[BoundingBox] = None, label: str = ""):
        if normalized:
            norm_x, norm_y = x, y
        else:
            norm_x = x / self.pixel_width
            norm_y = y / self.pixel_height

        # ResourceGuard pre-tap veto check
        if self.resource_guard is not None:
            target_label = label or getattr(box, "label", "")
            if self.resource_guard.is_vetoed_tap(norm_x, norm_y, label=target_label):
                import logging
                logging.getLogger("BotControl.MockDevice").critical(
                    f"🚫 [MOCK VETO STRICT] Thao tác tap_hold tại ({norm_x:.4f}, {norm_y:.4f}) với nhãn '{target_label}' bị chặn bởi ResourceGuard!"
                )
                return

        event = {
            "type": "tap_hold",
            "x": norm_x,
            "y": norm_y,
            "duration": duration,
            "box": box,
            "label": label,
            "timestamp": time.time(),
        }
        self.tap_history.append(event)
        self._client.tap_hold(norm_x, norm_y, duration=duration)

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.5, normalized: bool = True):
        if normalized:
            nx1, ny1, nx2, ny2 = x1, y1, x2, y2
        else:
            nx1, ny1, nx2, ny2 = x1 / self.pixel_width, y1 / self.pixel_height, x2 / self.pixel_width, y2 / self.pixel_height

        event = {
            "type": "swipe",
            "x1": nx1,
            "y1": ny1,
            "x2": nx2,
            "y2": ny2,
            "duration": duration,
            "timestamp": time.time(),
        }
        self.swipe_history.append(event)
        self._client.swipe(nx1, ny1, nx2, ny2, duration=duration)

    def start_frame_producer(self):
        self._producer_running = True

    def stop_frame_producer(self):
        self._producer_running = False

    @property
    def taps(self) -> List[Dict[str, Any]]:
        return self.tap_history

    @property
    def swipes(self) -> List[Dict[str, Any]]:
        return self.swipe_history

    def joystick_drag(self, angle_rad: float, magnitude: float = 1.0, duration: float = 0.5):
        import math
        from bot.core.coordinates import HSRZones
        center = HSRZones.JOYSTICK_CENTER
        max_r = HSRZones.JOYSTICK_MAX_RADIUS
        mag = max(0.1, min(1.0, magnitude))
        dist = max_r * mag
        target_x = center.x + math.cos(angle_rad) * dist
        target_y = center.y + math.sin(angle_rad) * dist
        self.swipe(center.x, center.y, target_x, target_y, duration=duration, normalized=True)

    def camera_pan(self, dx: float, dy: float, duration: float = 0.3):
        from bot.core.coordinates import HSRZones
        zone = HSRZones.CAMERA_SWIPE_ZONE
        start_x = zone.center.x
        start_y = zone.center.y
        end_x = max(zone.x1, min(zone.x2, start_x + dx))
        end_y = max(zone.y1, min(zone.y2, start_y + dy))
        self.swipe(start_x, start_y, end_x, end_y, duration=duration, normalized=True)

    def get_current_app(self) -> Optional[str]:
        return "com.HoYoverse.hkrpgoversea"

    def activate_game(self, bundle_id: str = "com.HoYoverse.hkrpgoversea") -> bool:
        return True

    def clear_history(self):
        self.tap_history.clear()
        self.swipe_history.clear()
        self._client.clear_history()



# =====================================================================
# Reference / Contract Implementations for M3 Interface Testing
# =====================================================================

class ReferenceFreshFrameGuard:
    """Timestamp guard ensuring pre-action cached frames are discarded."""

    def __init__(self, action_timestamp: float):
        self.action_timestamp = action_timestamp

    def is_fresh(self, frame_timestamp: float) -> bool:
        return frame_timestamp > self.action_timestamp


class ReferenceScreenStateTrigger:
    """Reference implementation of ScreenStateTrigger (PROJECT.md contract)."""

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
                # Fresh frame check if available
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
            # Check if OCRService has verify_roi_text
            if hasattr(self.ocr, "verify_roi_text"):
                return self.ocr.verify_roi_text(img, box, keywords)
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

            # Convert to grayscale for fast diff
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


class ReferenceFastChainExecutor:
    """Reference implementation of FastChainExecutor (PROJECT.md contract)."""

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

            # Dispatch tap through device to preserve 2D Gaussian point and touch hold
            if box is not None:
                self.device.tap(point.x, point.y, normalized=True, box=box)
            else:
                self.device.tap(point.x, point.y, normalized=True)

            # Apply Gaussian inter-tap cadence if not last target
            if i < len(targets) - 1:
                cadence = random.gauss(mean_cadence, std_cadence)
                clamped_cadence = max(0.105, min(0.200, cadence))
                time.sleep(clamped_cadence)

        return True


# Alias for backward and testing convenience
MockDevice = MockDeviceManager


class MockOCRService:
    """Mock OCR Service for testing tasks without RapidOCR engine."""

    def __init__(self):
        self.results: List[Any] = []

    def recognize(self, frame: np.ndarray, region: Optional[BoundingBox] = None) -> List[Any]:
        return list(self.results)

    def find_text(self, image: np.ndarray, target: str, region: Optional[BoundingBox] = None, min_similarity: float = 0.85):
        for r in self.results:
            if hasattr(r, "text") and target.lower() in r.text.lower():
                return r
        return None

    def find_any_text(self, image: np.ndarray, targets: List[str], region: Optional[BoundingBox] = None, min_similarity: float = 0.85):
        for t in targets:
            for r in self.results:
                if hasattr(r, "text") and t.lower() in r.text.lower():
                    return t, r
        return None


class MockTemplateMatcher:
    """Mock TemplateMatcher for testing tasks without OpenCV template files."""

    def __init__(self):
        self.matches: Dict[str, Optional[Tuple[BoundingBox, float]]] = {}

    def match(self, image: np.ndarray, template_name: str, threshold: float = 0.8, region: Optional[BoundingBox] = None, scales: Tuple[float, ...] = (1.0, 0.9, 1.1)):
        return self.matches.get(template_name, None)


