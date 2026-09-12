"""Device manager for iPad Pro M5 via WebDriverAgent."""
import base64
import io
import time
import logging
import socket
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, Union, Any
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


@dataclass(frozen=True)
class VideoFrame:
    """Immutable video frame container stored in double-buffered RAM."""
    frame_id: int
    timestamp: float
    jpeg_bytes: bytes
    width: int
    height: int
    _bgr: Optional[np.ndarray] = None

    def __init__(
        self,
        frame_id: int,
        timestamp: float,
        bgr: Optional[np.ndarray] = None,
        jpeg_bytes: bytes = b"",
        width: int = 2752,
        height: int = 2064,
        **kwargs,
    ):
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "jpeg_bytes", jpeg_bytes or kwargs.get("jpeg_bytes", b""))
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "_bgr", bgr)

    @property
    def bgr(self) -> Optional[np.ndarray]:
        val = self._bgr
        if val is None and self.jpeg_bytes:
            try:
                nparr = np.frombuffer(self.jpeg_bytes, np.uint8)
                val = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                object.__setattr__(self, "_bgr", val)
            except Exception:
                pass
        return val


class DeviceManager:
    """Manages iPad device connection via WebDriverAgent and screen interactions."""

    def __init__(self, wda_url: str = "http://127.0.0.1:8100", mjpeg_port: int = 9100, timeout: float = 30.0):
        self.wda_url = wda_url
        self.mjpeg_port = mjpeg_port
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

        # Async Frame Producer & Double-buffered RAM cache
        self._producer_thread: Optional[threading.Thread] = None
        self._producer_running = False
        self._frame_lock = threading.Lock()
        self._frame_condition = threading.Condition()
        self._front_frame: Optional[VideoFrame] = None
        self._frame_id_counter: int = 0
        self._gesture_in_progress = False

        # Legacy cached fields for 100% backward compatibility
        self._cached_bgr: Optional[np.ndarray] = None
        self._cached_jpeg: Optional[bytes] = None
        self._cached_time = 0.0

        # Zero-Spend ResourceGuard
        self.resource_guard: Optional[Any] = None

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

    def start_frame_producer(self):
        """Starts background worker to continuously stream frames into memory."""
        if self._producer_running:
            return
        self._producer_running = True
        self._producer_thread = threading.Thread(target=self._producer_loop, daemon=True, name="WDAFrameProducer")
        self._producer_thread.start()
        logger.info("Đã kích hoạt luồng Frame Producer bất đồng bộ (Async Stream Buffer)")

    def stop_frame_producer(self):
        self._producer_running = False

    def _normalize_to_bgr(self, shot: Any) -> Optional[np.ndarray]:
        """Converts raw shot (numpy array or PIL Image) to standard 3-channel BGR."""
        if shot is None:
            return None
        if isinstance(shot, np.ndarray):
            if len(shot.shape) == 2:
                return cv2.cvtColor(shot, cv2.COLOR_GRAY2BGR)
            elif shot.shape[2] == 4:
                return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
            elif shot.shape[2] == 3:
                return shot
        if hasattr(shot, "convert"):
            rgb = np.array(shot.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return None

    def _fetch_screenshot_bgr(self) -> Optional[np.ndarray]:
        """Captures screenshot bypassing namedlock via _unsafe_httpdo, with mock fallback."""
        # 1. If self._client is a mock or non-standard client, use client.screenshot()
        if self._client is not None and (
            not isinstance(self._client, wda.Client)
            or getattr(self._client, "_is_mock", False)
            or type(self._client).__name__.startswith("Mock")
        ):
            try:
                shot = self._client.screenshot()
                return self._normalize_to_bgr(shot)
            except Exception as e:
                logger.debug(f"Mock screenshot grab exception: {e}")
                return None

        # 2. Production path: bypass namedlock via _unsafe_httpdo
        try:
            url = f"{self.wda_url.rstrip('/')}/screenshot"
            res = wda._unsafe_httpdo(url, timeout=self.timeout)
            val = res.get("value") if isinstance(res, dict) else getattr(res, "value", None)
            if val:
                raw_bytes = base64.b64decode(val)
                nparr = np.frombuffer(raw_bytes, np.uint8)
                bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if bgr is not None:
                    return bgr
        except Exception as e:
            logger.debug(f"Direct _unsafe_httpdo capture failed: {e}")

        # 3. Fallback to self._client.screenshot() if direct HTTP failed
        if self._client is not None and hasattr(self._client, "screenshot"):
            try:
                shot = self._client.screenshot()
                return self._normalize_to_bgr(shot)
            except Exception as e:
                logger.debug(f"Fallback client screenshot failed: {e}")

        return None

    def _update_front_frame(self, bgr_arr: np.ndarray) -> VideoFrame:
        """Encodes 960x720 JPEG Q72, constructs VideoFrame, and performs atomic pointer swap."""
        ph, pw = bgr_arr.shape[:2]
        if pw != self.pixel_width or ph != self.pixel_height:
            self.pixel_width = pw
            self.pixel_height = ph
            self.coords.update_resolution(pw, ph)

        # Optimize for ultra-smooth web streaming (960x720 4:3 iPad ratio)
        small = cv2.resize(bgr_arr, (960, 720), interpolation=cv2.INTER_AREA)
        ret, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 72])
        jpeg_bytes = buf.tobytes() if ret else b""

        now = time.time()
        self._frame_id_counter += 1
        new_frame = VideoFrame(
            frame_id=self._frame_id_counter,
            timestamp=now,
            bgr=bgr_arr,
            jpeg_bytes=jpeg_bytes,
            width=pw,
            height=ph,
        )

        # Atomic pointer swap under Python GIL
        self._front_frame = new_frame

        # Legacy fields updated for 100% backward compatibility
        with self._frame_lock:
            self._cached_bgr = bgr_arr
            self._cached_jpeg = jpeg_bytes
            self._cached_time = now
            self.last_screenshot = bgr_arr
            self.last_screenshot_time = now
            self.last_screenshot_bytes = jpeg_bytes

        with self._frame_condition:
            self._frame_condition.notify_all()

        return new_frame

    def _update_front_frame_from_jpeg(self, jpeg_bytes: bytes) -> VideoFrame:
        """Constructs VideoFrame directly from hardware JPEG bytes without decoding BGR upfront."""
        now = time.time()
        self._frame_id_counter += 1
        new_frame = VideoFrame(
            frame_id=self._frame_id_counter,
            timestamp=now,
            jpeg_bytes=jpeg_bytes,
            width=self.pixel_width,
            height=self.pixel_height,
        )
        self._front_frame = new_frame
        with self._frame_lock:
            self._cached_jpeg = jpeg_bytes
            self._cached_time = now
            self.last_screenshot_bytes = jpeg_bytes
            self.last_screenshot_time = now
            self._cached_bgr = None  # Invalidate cached BGR

        with self._frame_condition:
            self._frame_condition.notify_all()

        return new_frame

    def _producer_loop(self):
        """Continuous background loop capturing frames from native WDA MJPEG socket or fallback."""
        logger.info("Frame Producer Loop started.")
        while self._producer_running:
            if not self.connected:
                if not self.connect():
                    time.sleep(1.0)
                    continue

            # Try native socket connection on port 9100 for hardware 40-60 FPS streaming
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect(("127.0.0.1", self.mjpeg_port))
                sock.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:9100\r\n\r\n")
                boundary = b"--BoundaryString"
                buf = b""
                logger.info(f"Connected to native WDA hardware MJPEG stream on port {self.mjpeg_port} (High-Speed Direct)")

                while self._producer_running:
                    if self._gesture_in_progress:
                        time.sleep(0.01)
                        continue

                    chunk = sock.recv(32768)
                    if not chunk:
                        break
                    buf += chunk
                    while boundary in buf:
                        idx = buf.find(boundary)
                        header_end = buf.find(b"\r\n\r\n", idx)
                        if header_end != -1:
                            next_b = buf.find(boundary, header_end)
                            if next_b != -1:
                                raw_chunk = buf[header_end + 4 : next_b]
                                soi = raw_chunk.find(b"\xff\xd8")
                                eoi = raw_chunk.rfind(b"\xff\xd9")
                                if soi != -1 and eoi != -1 and eoi > soi:
                                    clean_jpeg = raw_chunk[soi : eoi + 2]
                                    self._update_front_frame_from_jpeg(clean_jpeg)
                                buf = buf[next_b:]
                            else:
                                break
                        else:
                            break
            except Exception as e:
                logger.debug(f"Native MJPEG socket closed/unreachable ({e}). Falling back to HTTP capture.")
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

            # Fallback HTTP loop if native socket breaks or during unit/mock tests
            while self._producer_running:
                if self._gesture_in_progress:
                    time.sleep(0.016)
                    continue

                try:
                    bgr_arr = self._fetch_screenshot_bgr()
                    if bgr_arr is not None:
                        self._update_front_frame(bgr_arr)
                    time.sleep(0.016)  # 60 FPS target in fallback
                except Exception as e:
                    logger.debug(f"Fallback frame grab exception: {e}")
                    time.sleep(0.2)
                    break

    def get_video_frame(self) -> Optional[VideoFrame]:
        """Returns the latest VideoFrame from memory (0.0ms lock-free access under GIL)."""
        return self._front_frame

    def get_screenshot(self, force_fresh: bool = False, max_age: float = 0.20) -> Optional[np.ndarray]:
        """Captures or returns a screenshot from RAM cache (0.0ms) or direct WDA."""
        now = time.time()
        frame = self._front_frame
        if not force_fresh and frame is not None and (now - frame.timestamp) < max_age:
            return frame.bgr

        # Legacy cache fallback
        if not force_fresh and self._cached_bgr is not None and (now - self._cached_time) < max_age:
            return self._cached_bgr

        # Fallback to direct capture if producer is not running or cache stale
        if not self.connected and not self.connect():
            return None

        bgr_arr = self._fetch_screenshot_bgr()
        if bgr_arr is not None:
            self._update_front_frame(bgr_arr)
            return bgr_arr

        return None

    def get_screenshot_jpeg_bytes(self) -> Optional[bytes]:
        """Returns pre-encoded JPEG bytes directly from RAM in 0.0ms for zero-latency video streaming."""
        frame = self._front_frame
        if frame is not None and frame.jpeg_bytes:
            return frame.jpeg_bytes
        if self._cached_jpeg is not None:
            return self._cached_jpeg

        img = self.get_screenshot()
        if img is not None:
            small = cv2.resize(img, (960, 720), interpolation=cv2.INTER_AREA)
            ret, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if ret:
                jpeg_bytes = buf.tobytes()
                with self._frame_lock:
                    self._cached_jpeg = jpeg_bytes
                return jpeg_bytes
        return self.last_screenshot_bytes

    def tap(self, x: float, y: float, normalized: bool = True, box: Optional[BoundingBox] = None, label: str = ""):
        """Taps at coordinate with optional 2D Gaussian human dispersion and biological contact duration."""
        if not self.connected and not self.connect():
            logger.warning("Không thể gửi tap: WDA chưa kết nối")
            return

        if normalized:
            norm_x = float(max(0.0, min(1.0, x)))
            norm_y = float(max(0.0, min(1.0, y)))
        else:
            target_w = self.pixel_width
            target_h = self.pixel_height
            if self._front_frame is not None and self._front_frame.bgr is not None:
                fh, fw = self._front_frame.bgr.shape[:2]
                if x <= fw and y <= fh:
                    target_w, target_h = fw, fh
            norm_x = float(max(0.0, min(1.0, x / target_w)))
            norm_y = float(max(0.0, min(1.0, y / target_h)))

        # ResourceGuard pre-tap veto check
        if self.resource_guard is not None:
            target_label = label or getattr(box, "label", "")
            if self.resource_guard.is_vetoed_tap(norm_x, norm_y, label=target_label):
                logger.critical(f"🚫 [VETO STRICT] Thao tác tap tại ({norm_x:.4f}, {norm_y:.4f}) với nhãn '{target_label}' bị chặn bởi ResourceGuard!")
                return

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

    def tap_hold(self, x: float, y: float, duration: float = 0.1, normalized: bool = True, box: Optional[BoundingBox] = None, label: str = ""):
        """Taps and holds at coordinate for specified duration."""
        if not self.connected and not self.connect():
            logger.warning("Không thể gửi tap_hold: WDA chưa kết nối")
            return

        if normalized:
            norm_x = float(max(0.0, min(1.0, x)))
            norm_y = float(max(0.0, min(1.0, y)))
        else:
            target_w = self.pixel_width
            target_h = self.pixel_height
            if self._front_frame is not None and self._front_frame.bgr is not None:
                fh, fw = self._front_frame.bgr.shape[:2]
                if x <= fw and y <= fh:
                    target_w, target_h = fw, fh
            norm_x = float(max(0.0, min(1.0, x / target_w)))
            norm_y = float(max(0.0, min(1.0, y / target_h)))

        # ResourceGuard pre-tap veto check
        if self.resource_guard is not None:
            target_label = label or getattr(box, "label", "")
            if self.resource_guard.is_vetoed_tap(norm_x, norm_y, label=target_label):
                logger.critical(f"🚫 [VETO STRICT] Thao tác tap_hold tại ({norm_x:.4f}, {norm_y:.4f}) với nhãn '{target_label}' bị chặn bởi ResourceGuard!")
                return

        if self.enable_human_touch:
            hp = generate_gaussian_point(Point(norm_x, norm_y), box=box)
            norm_x = float(max(0.005, min(0.995, hp.x)))
            norm_y = float(max(0.005, min(0.995, hp.y)))

        logger.info(f"Thực hiện tap_hold tại ({norm_x:.4f}, {norm_y:.4f}) [giữ {duration*1000:.0f}ms]")
        try:
            self._client.tap_hold(norm_x, norm_y, duration=duration)
        except Exception as e:
            logger.error(f"Lỗi gửi tap_hold: {e}")

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

        self._gesture_in_progress = True
        try:
            self._client.swipe(float(nx1), float(ny1), float(nx2), float(ny2), duration=duration)
        except Exception as e:
            logger.error(f"Lỗi gửi swipe: {e}")
        finally:
            self._gesture_in_progress = False
