"""Unit tests for Human-like Touch Engine & Anti-Ban defense."""
import unittest
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import (
    generate_gaussian_point,
    generate_bezier_trajectory,
    random_touch_duration,
    cognitive_delay,
    ThreatDetector,
)


class TestHumanTouch(unittest.TestCase):

    def test_gaussian_point_dispersion(self):
        """Tests that 1000 sample points stay strictly within bounding box and disperse naturally."""
        box = BoundingBox(100, 200, 300, 400)
        center = box.center  # (200, 300)

        points = [generate_gaussian_point(center, box=box, spread_ratio=0.5) for _ in range(1000)]

        # Check containment
        for p in points:
            self.assertTrue(box.contains(p), f"Point {p} outside bounding box {box}")

        # Check diversity (no two points identical)
        unique_coords = set((round(p.x, 3), round(p.y, 3)) for p in points)
        self.assertGreater(len(unique_coords), 980)

        # Check mean is close to center
        avg_x = sum(p.x for p in points) / len(points)
        avg_y = sum(p.y for p in points) / len(points)
        self.assertAlmostEqual(avg_x, center.x, delta=3.0)
        self.assertAlmostEqual(avg_y, center.y, delta=3.0)

    def test_touch_duration(self):
        """Tests touch duration is within biological human range."""
        durations = [random_touch_duration() for _ in range(100)]
        for d in durations:
            self.assertGreaterEqual(d, 0.080)
            self.assertLessEqual(d, 0.220)
        # Check variance
        self.assertGreater(len(set(durations)), 80)

    def test_bezier_trajectory(self):
        """Tests Bezier trajectory generation for swipe gestures."""
        start = Point(0.2, 0.7)
        end = Point(0.2, 0.3)
        trajectory = generate_bezier_trajectory(start, end, num_points=25)

        self.assertEqual(len(trajectory), 25)
        # Start and end approximately match
        self.assertAlmostEqual(trajectory[0][0], start.x, places=2)
        self.assertAlmostEqual(trajectory[0][1], start.y, places=2)
        self.assertAlmostEqual(trajectory[-1][0], end.x, places=2)
        self.assertAlmostEqual(trajectory[-1][1], end.y, places=2)

        # Velocity profile (dt is greater at ends and smaller in the middle)
        dt_start = trajectory[0][2]
        dt_mid = trajectory[12][2]
        self.assertGreater(dt_start, dt_mid)

    def test_threat_detector(self):
        """Tests security and Captcha prompt detection."""
        threat_samples = [
            ["Cài đặt", "Xác minh bảo mật", "Đồng ý"],
            ["Kéo mảnh ghép vào vị trí"],
            ["Phát hiện hành vi bất thường, vui lòng tạm dừng"],
            ["Security check required: Captcha"],
        ]
        for sample in threat_samples:
            detected, msg = ThreatDetector.check_for_threats(sample)
            self.assertTrue(detected, f"Failed to detect threat in {sample}")

        safe_samples = [
            ["Huấn Luyện Thường Ngày", "Hướng Dẫn Sinh Tồn", "Vào", "Nhận"],
            ["Sức Mạnh Khai Phá", "Đài Hoa Nhân Tạo (Vàng)", "40"],
            ["Bắt Đầu Khiêu Chiến", "Thách Đấu Lại", "Rút Lui"],
        ]
        for sample in safe_samples:
            detected, _ = ThreatDetector.check_for_threats(sample)
            self.assertFalse(detected, f"False positive in {sample}")


if __name__ == "__main__":
    unittest.main()
