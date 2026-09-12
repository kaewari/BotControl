"""Unit tests for UICoordinateCache and Micro-ROI verification."""
import os
import unittest
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.cache import UICoordinateCache, DEFAULT_CACHE
from bot.cv.ocr_service import OCRService


class TestUICache(unittest.TestCase):

    def setUp(self):
        self.test_cache_file = "/tmp/test_ui_cache.json"
        if os.path.exists(self.test_cache_file):
            os.remove(self.test_cache_file)
        self.cache = UICoordinateCache(filepath=self.test_cache_file)

    def tearDown(self):
        if os.path.exists(self.test_cache_file):
            os.remove(self.test_cache_file)

    def test_default_buttons_loaded(self):
        """Tests that all essential buttons exist in default cache."""
        required_keys = [
            "phone_menu_icon",
            "phone_assignments",
            "guidebook_icon",
            "guidebook_close",
            "tab_daily_training",
            "tab_survival_index",
            "chest_100",
            "chest_500",
            "target_relic_enter",
            "dungeon_challenge_btn",
            "team_start_battle_btn",
            "battle_retreat_btn",
        ]
        for k in required_keys:
            pt = self.cache.get_point(k)
            self.assertIsNotNone(pt, f"Key {k} missing from cache")
            self.assertTrue(0.0 <= pt.x <= 1.0)
            self.assertTrue(0.0 <= pt.y <= 1.0)

    def test_cache_update_and_persistence(self):
        """Tests that updating a coordinate persists across reload."""
        self.cache.update("custom_btn", 0.777, 0.888, label="Custom Button")
        pt = self.cache.get_point("custom_btn")
        self.assertEqual(pt.x, 0.777)
        self.assertEqual(pt.y, 0.888)

        # Reload cache from disk
        reloaded_cache = UICoordinateCache(filepath=self.test_cache_file)
        pt2 = reloaded_cache.get_point("custom_btn")
        self.assertIsNotNone(pt2)
        self.assertEqual(pt2.x, 0.777)
        self.assertEqual(pt2.y, 0.888)

    def test_verify_roi_text(self):
        """Tests Micro-ROI fast text check."""
        # Create a synthetic image with text
        ocr = OCRService()
        img = np.ones((500, 500, 3), dtype=np.uint8) * 255
        import cv2
        cv2.putText(img, "Uy Thac", (200, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        # Micro-ROI centered at (0.5, 0.5) should find "Uy Thac"
        found = ocr.verify_roi_text(img, ["Uy Thac", "Ủy Thác"], Point(0.5, 0.5), roi_radius_norm=0.25)
        self.assertTrue(found)

        # Micro-ROI far away at (0.1, 0.1) should return False
        found_far = ocr.verify_roi_text(img, ["Uy Thac"], Point(0.1, 0.1), roi_radius_norm=0.08)
        self.assertFalse(found_far)


if __name__ == "__main__":
    unittest.main()
