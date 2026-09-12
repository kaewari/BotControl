"""Unit tests for 3D navigation, Minimap tracking, and Visual Servoing."""
import math
import unittest
import numpy as np
import cv2

from bot.core.coordinates import Point, BoundingBox, HSRZones
from bot.cv.navigation import MinimapTracker, QuestMarkerDetector, VisualServoingController


class TestNavigation(unittest.TestCase):

    def setUp(self):
        self.tracker = MinimapTracker()
        self.detector = QuestMarkerDetector()
        self.controller = VisualServoingController()

    def test_extract_minimap_crop(self):
        # Create a synthetic 1000x800 test frame
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        crop, x1, y1 = self.tracker.extract_minimap_crop(frame)
        self.assertGreater(crop.shape[0], 0)
        self.assertGreater(crop.shape[1], 0)
        self.assertEqual(x1, int(HSRZones.MINIMAP_BOUNDS.x1 * 1000))
        self.assertEqual(y1, int(HSRZones.MINIMAP_BOUNDS.y1 * 800))

    def test_detect_player_heading_none_on_blank(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        heading = self.tracker.detect_player_heading(frame)
        self.assertIsNone(heading)

    def test_detect_quest_marker_synthetic(self):
        # Create a frame with a golden diamond marker at (500, 400)
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        # BGR color for gold/yellow in game HSV range
        # HSV [25, 200, 240] -> BGR ≈ (30, 200, 240)
        pts = np.array([[500, 385], [515, 400], [500, 415], [485, 400]], dtype=np.int32)
        cv2.fillPoly(frame, [pts], (30, 200, 240))

        res = self.detector.detect_quest_marker(frame)
        self.assertIsNotNone(res)
        pt, conf = res
        self.assertAlmostEqual(pt.x, 0.50, delta=0.03)
        self.assertAlmostEqual(pt.y, 0.40, delta=0.03)
        self.assertGreater(conf, 0.5)

    def test_detect_quest_marker_none_on_blank(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        res = self.detector.detect_quest_marker(frame)
        self.assertIsNone(res)

    def test_compute_steering_centered(self):
        # Marker is directly in front at (0.50, 0.45)
        marker = Point(0.50, 0.45)
        pan_dx, pan_dy, angle, mag = self.controller.compute_steering(marker)
        self.assertEqual(pan_dx, 0.0)  # Within deadzone
        self.assertEqual(pan_dy, 0.0)
        self.assertAlmostEqual(angle, -math.pi / 2.0, places=2)  # Straight forward
        self.assertEqual(mag, 1.0)  # Full speed

    def test_compute_steering_marker_to_right(self):
        # Marker is on the right side of the screen at (0.80, 0.45)
        marker = Point(0.80, 0.45)
        pan_dx, pan_dy, angle, mag = self.controller.compute_steering(marker)
        self.assertLess(pan_dx, 0.0)  # Pan camera left to bring right object center
        self.assertGreater(angle, -math.pi / 2.0)  # Steer joystick toward right
        self.assertLess(mag, 1.0)  # Slower when steering

    def test_compute_steering_marker_missing(self):
        # No marker: slow camera search scan
        pan_dx, pan_dy, angle, mag = self.controller.compute_steering(None)
        self.assertGreater(pan_dx, 0.0)
        self.assertAlmostEqual(angle, -math.pi / 2.0)
        self.assertAlmostEqual(mag, 0.50)

    def test_anti_stuck_detection(self):
        controller = VisualServoingController()
        # Feed identical frames 4 times
        static_frame = np.zeros((400, 400, 3), dtype=np.uint8)
        stuck_results = [controller.update_stuck_state(static_frame) for _ in range(6)]
        self.assertTrue(any(stuck_results))
        controller.reset_stuck()
        self.assertFalse(controller.update_stuck_state(static_frame))


if __name__ == "__main__":
    unittest.main()
