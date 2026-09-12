"""3D Overworld Navigation, Minimap Tracking, and Quest Marker Visual Servoing for Honkai: Star Rail."""
import math
import time
import logging
from typing import Optional, Tuple, List, Dict, Any
import cv2
import numpy as np

from bot.core.coordinates import Point, BoundingBox, HSRZones

logger = logging.getLogger("BotControl.Navigation")


class MinimapTracker:
    """Tracks player position, heading orientation, and boundary markers on the minimap."""

    def __init__(self, bounds: Optional[BoundingBox] = None):
        self.bounds = bounds or HSRZones.MINIMAP_BOUNDS

    def extract_minimap_crop(self, frame: np.ndarray) -> Tuple[np.ndarray, int, int]:
        """Crops the minimap area from a full screen frame."""
        h, w = frame.shape[:2]
        x1 = int(self.bounds.x1 * w)
        y1 = int(self.bounds.y1 * h)
        x2 = int(self.bounds.x2 * w)
        y2 = int(self.bounds.y2 * h)
        crop = frame[y1:y2, x1:x2]
        return crop, x1, y1

    def detect_player_heading(self, frame: np.ndarray) -> Optional[float]:
        """Detects the player heading angle in degrees [0, 360) from minimap center arrow.
        
        0° represents facing North (up), 90° East (right), 180° South (down), 270° West (left).
        """
        if frame is None:
            return None
        crop, x1, y1 = self.extract_minimap_crop(frame)
        if crop.size == 0:
            return None

        ch, cw = crop.shape[:2]
        center_x, center_y = cw // 2, ch // 2
        radius = min(cw, ch) // 5

        # Crop central area where player arrow resides
        roi = crop[max(0, center_y - radius):min(ch, center_y + radius),
                   max(0, center_x - radius):min(cw, center_x + radius)]
        if roi.size == 0:
            return None

        # Convert to HSV and isolate the bright player pointer (cyan/blue or bright white arrow)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Blue / Cyan arrow mask
        mask_blue = cv2.inRange(hsv, np.array([85, 100, 150]), np.array([125, 255, 255]))
        # White highlight mask
        mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 45, 255]))
        combined = cv2.bitwise_or(mask_blue, mask_white)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # Find largest contour in the center
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 15:
            return None

        # Calculate moments or fit ellipse/line to find heading direction
        if len(largest) >= 5:
            (x, y), (MA, ma), angle = cv2.fitEllipse(largest)
            return float(angle)
        else:
            # Fallback to center of mass offset
            M = cv2.moments(largest)
            if M["m00"] > 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                dx = cx - (roi.shape[1] / 2.0)
                dy = cy - (roi.shape[0] / 2.0)
                angle_rad = math.atan2(dy, dx)
                deg = (math.degrees(angle_rad) + 90) % 360
                return float(deg)

        return None


class QuestMarkerDetector:
    """Detects the 3D overworld golden quest marker (✦ / diamond) and interaction prompts."""

    # HSV color bounds for the distinct golden/yellow quest indicator
    LOWER_GOLD = np.array([16, 120, 160])
    UPPER_GOLD = np.array([38, 255, 255])

    def __init__(self):
        pass

    def detect_quest_marker(self, frame: np.ndarray) -> Optional[Tuple[Point, float]]:
        """Scans the screen for the 3D golden quest marker.
        
        Returns:
            (Point(norm_x, norm_y), confidence) or None if not visible.
        """
        if frame is None:
            return None

        h, w = frame.shape[:2]
        # Exclude UI overlays (minimap on top-left, HUD buttons on top-right)
        search_roi = frame.copy()
        # Blank out top bar and minimap to prevent false positives from UI icons
        search_roi[0:int(h * 0.18), 0:int(w * 0.25)] = 0
        search_roi[0:int(h * 0.15), int(w * 0.55):w] = 0
        # Blank out character status bar at right
        search_roi[int(h * 0.25):int(h * 0.65), int(w * 0.80):w] = 0

        hsv = cv2.cvtColor(search_roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.LOWER_GOLD, self.UPPER_GOLD)

        # Morphological filtering to clean noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 30 < area < 4000:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / float(ch) if ch > 0 else 0
                if 0.5 <= aspect <= 2.0:
                    cx = (x + cw / 2.0) / float(w)
                    cy = (y + ch / 2.0) / float(h)
                    score = min(1.0, area / 200.0)
                    candidates.append((Point(cx, cy), score))

        if not candidates:
            return None

        # Return candidate closest to screen center or with highest score
        candidates.sort(key=lambda item: (abs(item[0].x - 0.50) + abs(item[0].y - 0.45)))
        return candidates[0]

    def detect_interaction_prompt(self, frame: np.ndarray, ocr_service: Any) -> Optional[Tuple[Point, str]]:
        """Detects whether an interactive dialogue prompt / action bubble is visible."""
        if frame is None or ocr_service is None:
            return None

        h, w = frame.shape[:2]
        box = HSRZones.INTERACTION_PROMPT_BOX
        x1, y1 = int(box.x1 * w), int(box.y1 * h)
        x2, y2 = int(box.x2 * w), int(box.y2 * h)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        results = ocr_service.recognize(crop)
        keywords = ["Nói chuyện", "Noi chuyen", "Điều tra", "Dieu tra", "Mở", "Mo", "Tương tác", "Kích hoạt", "Vào"]
        for r in results:
            for kw in keywords:
                if kw.lower() in r.text.lower():
                    # Calculate normalized coordinates in full screen
                    abs_cx = (x1 + r.center.x) / float(w)
                    abs_cy = (y1 + r.center.y) / float(h)
                    return Point(abs_cx, abs_cy), r.text

        return None


class VisualServoingController:
    """Calculates smooth camera rotations and joystick vectors to navigate toward 3D objectives."""

    def __init__(self, deadzone_x: float = 0.06):
        self.deadzone_x = deadzone_x
        self.last_minimap_hashes: List[int] = []
        self.stuck_counter = 0

    def compute_steering(self, marker_point: Optional[Point]) -> Tuple[float, float, float, float]:
        """Calculates camera adjustment (pan_dx, pan_dy) and joystick move (angle_rad, magnitude).
        
        Returns:
            (pan_dx, pan_dy, joystick_angle_rad, joystick_magnitude)
        """
        # Default angle is straight forward (-pi/2)
        forward_angle = -math.pi / 2.0

        if marker_point is None:
            # Marker not visible: slowly rotate camera to search (pan left/right)
            return 0.18, 0.0, forward_angle, 0.50

        err_x = marker_point.x - 0.50
        err_y = marker_point.y - 0.45

        # Pan camera to keep marker centered
        if abs(err_x) > self.deadzone_x:
            # Move camera opposite to error to center it
            pan_dx = float(np.clip(-err_x * 0.45, -0.25, 0.25))
        else:
            pan_dx = 0.0

        pan_dy = float(np.clip(-err_y * 0.15, -0.08, 0.08)) if abs(err_y) > 0.15 else 0.0

        # Joystick heading: angle is biased toward marker
        steer_offset = err_x * 0.6  # Radians
        joystick_angle = forward_angle + steer_offset

        # Magnitude: slower when turning sharply, full speed when aligned
        alignment = max(0.4, 1.0 - abs(err_x) * 1.5)
        joystick_mag = float(np.clip(alignment, 0.45, 1.0))

        return pan_dx, pan_dy, joystick_angle, joystick_mag

    def update_stuck_state(self, frame: np.ndarray) -> bool:
        """Monitors visual flow to detect if the character is stuck against a wall or obstacle.
        
        Returns True if stuck for >= 3 checks (~1.5s).
        """
        if frame is None:
            return False

        h, w = frame.shape[:2]
        # Small center sample
        sample = cv2.resize(frame[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)], (32, 32))
        f_hash = int(np.sum(sample))

        self.last_minimap_hashes.append(f_hash)
        if len(self.last_minimap_hashes) > 6:
            self.last_minimap_hashes.pop(0)

        if len(self.last_minimap_hashes) >= 4:
            # Check variance across last frames
            var = np.var(self.last_minimap_hashes)
            if var < 150:  # Screen hasn't changed despite moving
                self.stuck_counter += 1
                if self.stuck_counter >= 3:
                    logger.warning("⚠️ [ANTI-STUCK] Phát hiện nhân vật bị kẹt vật cản!")
                    return True
            else:
                self.stuck_counter = 0

        return False

    def reset_stuck(self):
        self.stuck_counter = 0
        self.last_minimap_hashes.clear()
