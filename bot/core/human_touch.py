"""Human-like Touch Engine & Anti-Ban Defense Module.
Provides 2D Gaussian coordinate dispersion, Bezier curve gesture trajectories,
cognitive timing jitter, and real-time threat/captcha detection.
"""
import math
import random
import time
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

from bot.core.coordinates import Point, BoundingBox

logger = logging.getLogger("BotControl.HumanTouch")


def generate_gaussian_point(
    center: Point,
    box: Optional[BoundingBox] = None,
    spread_ratio: float = 0.35,
) -> Point:
    """Generates a randomized touch point using 2D Truncated Gaussian distribution around the target center.
    Never clicks the exact same pixel twice.
    """
    if box is None:
        # Default radius ~ 1.5% of screen
        dx = random.gauss(0, 0.008)
        dy = random.gauss(0, 0.008)
        # Clamp to avoid excessive drift
        dx = max(-0.02, min(0.02, dx))
        dy = max(-0.02, min(0.02, dy))
        return Point(center.x + dx, center.y + dy)

    # Calculate half-dimensions
    half_w = (box.x2 - box.x1) * 0.5
    half_h = (box.y2 - box.y1) * 0.5

    # 3-sigma rule: 99.7% of points fall within spread_ratio * half dimension
    sigma_x = (half_w * spread_ratio) / 2.5
    sigma_y = (half_h * spread_ratio) / 2.5

    # Generate Gaussian offset
    offset_x = random.gauss(0, sigma_x)
    offset_y = random.gauss(0, sigma_y)

    # Truncate strictly within inner safe zone (spread_ratio * half dimension)
    offset_x = max(-half_w * spread_ratio, min(half_w * spread_ratio, offset_x))
    offset_y = max(-half_h * spread_ratio, min(half_h * spread_ratio, offset_y))

    return Point(center.x + offset_x, center.y + offset_y)


def generate_bezier_trajectory(
    start: Point,
    end: Point,
    num_points: int = 24,
    deviation: float = 0.035,
    micro_jitter: float = 0.0015,
) -> List[Tuple[float, float, float]]:
    """Generates a human-like swipe trajectory using Cubic Bezier curve with micro-tremors
    and non-linear acceleration-deceleration timing profile.
    Returns list of (x, y, sleep_dt).
    """
    p0 = np.array([start.x, start.y], dtype=float)
    p3 = np.array([end.x, end.y], dtype=float)

    # Vector and normal vector
    vec = p3 - p0
    dist = np.linalg.norm(vec)
    if dist < 1e-5:
        return [(start.x, start.y, 0.01)]

    unit_vec = vec / dist
    normal_vec = np.array([-unit_vec[1], unit_vec[0]])

    # Random curvature direction and scale
    side = random.choice([-1.0, 1.0])
    curve_scale1 = random.uniform(0.3, 1.0) * deviation * side
    curve_scale2 = random.uniform(0.3, 1.0) * deviation * side

    # Control points C1 and C2
    c1 = p0 + vec * random.uniform(0.2, 0.4) + normal_vec * curve_scale1
    c2 = p0 + vec * random.uniform(0.6, 0.8) + normal_vec * curve_scale2

    # Generate points along Bezier curve
    t_values = np.linspace(0.0, 1.0, num_points)
    trajectory = []

    # Non-linear velocity profile (ease-in ease-out)
    for i, t in enumerate(t_values):
        # Cubic Bezier formula: (1-t)^3*P0 + 3(1-t)^2*t*C1 + 3(1-t)*t^2*C2 + t^3*P3
        pos = (
            (1 - t) ** 3 * p0
            + 3 * (1 - t) ** 2 * t * c1
            + 3 * (1 - t) * t ** 2 * c2
            + t ** 3 * p3
        )

        # Add slight natural hand tremor (micro-jitter)
        if 0 < i < num_points - 1:
            wobble = np.random.normal(0, micro_jitter, 2)
            pos += wobble

        # Velocity curve: slower at ends, faster in the middle
        v_factor = math.sin(t * math.pi)  # 0 at start/end, 1 at midpoint
        dt = 0.022 - 0.012 * v_factor + random.uniform(-0.002, 0.002)
        dt = max(0.006, dt)

        trajectory.append((float(pos[0]), float(pos[1]), float(dt)))

    return trajectory


def random_touch_duration(min_ms: int = 85, max_ms: int = 210) -> float:
    """Returns randomized finger contact duration in seconds (mimicking biological tap)."""
    val_ms = random.gauss(140, 25)
    val_ms = max(min_ms, min(max_ms, val_ms))
    return val_ms / 1000.0


def cognitive_delay(
    mean: float = 1.2,
    std: float = 0.35,
    min_sec: float = 0.4,
    max_sec: float = 3.5,
) -> float:
    """Generates human cognitive thinking pause."""
    delay = random.gauss(mean, std)
    return max(min_sec, min(max_sec, delay))


class ThreatDetector:
    """Real-time screen inspector for security verifications, captchas, and unusual prompts."""

    THREAT_KEYWORDS = [
        "xác minh",
        "xac minh",
        "kéo thanh trượt",
        "keo thanh truat",
        "mảnh ghép",
        "manh ghep",
        "bảo mật",
        "bao mat",
        "captcha",
        "verification",
        "security check",
        "bất thường",
        "bat thuong",
        "tạm khóa",
        "tam khoa",
        "vi phạm",
        "vi pham",
    ]

    @classmethod
    def check_for_threats(cls, text_list: List[str]) -> Tuple[bool, Optional[str]]:
        """Scans recognized texts for security threats or Captcha prompts."""
        for raw_text in text_list:
            lower = raw_text.lower().strip()
            for kw in cls.THREAT_KEYWORDS:
                if kw in lower:
                    logger.critical(f"🚨 PHÁT HIỆN DẤU HIỆU BẢO MẬT / CAPTCHA: '{raw_text}' (Từ khóa: '{kw}')")
                    return True, f"Phát hiện cảnh báo bảo mật: '{raw_text}'"
        return False, None
