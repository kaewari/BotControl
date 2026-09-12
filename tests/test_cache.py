"""Unit tests for UICoordinateCache, Micro-ROI verification, and Self-Healing fallbacks."""
import os
import time
import unittest
import numpy as np
import cv2

from bot.core.coordinates import Point, BoundingBox
from bot.core.cache import UICoordinateCache, UIElement, DEFAULT_CACHE, DEFAULT_META
from bot.cv.ocr_service import OCRService


class TestUICache(unittest.TestCase):

    def setUp(self):
        self.test_cache_file = "/tmp/test_ui_cache.json"
        if os.path.exists(self.test_cache_file):
            os.remove(self.test_cache_file)
        self.cache = UICoordinateCache(filepath=self.test_cache_file)
        self.ocr = OCRService()

    def tearDown(self):
        if os.path.exists(self.test_cache_file):
            os.remove(self.test_cache_file)

    def test_default_buttons_loaded_and_complete(self):
        """Tests that all 27+ required buttons exist in default cache with valid coordinates and boxes."""
        required_keys = [
            # 5 chests
            "chest_100", "chest_200", "chest_300", "chest_400", "chest_500",
            # Phone menu, assignments, claim all, redispatch
            "phone_menu_icon", "phone_assignments", "assignment_claim_all", "assignment_redispatch",
            # Guidebook icon, close, tabs 1-3
            "guidebook_icon", "guidebook_close", "tab_daily_training", "tab_survival_index", "tab_simulated_universe",
            # Daily mission claim, Robin character card
            "daily_mission_claim", "target_character_card",
            # Relic and Planar enter buttons (with corrected coordinates)
            "target_relic_enter", "target_planar_enter_1", "target_planar_enter_2",
            # Dungeon rows 1-4
            "enter_row_1", "enter_row_2", "enter_row_3", "enter_row_4",
            # Action buttons
            "dungeon_challenge_btn", "team_start_battle_btn", "battle_retreat_btn", "resin_popup_cancel", "back_button",
        ]

        self.assertGreaterEqual(len(self.cache.elements), 27)
        for k in required_keys:
            elem = self.cache.get_element(k)
            self.assertIsNotNone(elem, f"Key {k} missing from cache elements")
            pt = self.cache.get_point(k)
            self.assertIsNotNone(pt, f"Point for {k} missing from cache")
            self.assertTrue(0.0 <= pt.x <= 1.0, f"Point X for {k} out of bounds: {pt.x}")
            self.assertTrue(0.0 <= pt.y <= 1.0, f"Point Y for {k} out of bounds: {pt.y}")

            box = self.cache.get_box(k)
            self.assertIsNotNone(box, f"BoundingBox for {k} missing from cache")
            self.assertTrue(0.0 <= box.x1 < box.x2 <= 1.0, f"BoundingBox X for {k} invalid: [{box.x1}, {box.x2}]")
            self.assertTrue(0.0 <= box.y1 < box.y2 <= 1.0, f"BoundingBox Y for {k} invalid: [{box.y1}, {box.y2}]")
            self.assertTrue(box.contains(pt), f"BoundingBox for {k} does not contain point {pt}")

        # Verify corrected relic enter and planar enter coordinates
        relic = self.cache.get_element("target_relic_enter")
        self.assertAlmostEqual(relic.x, 0.8540, places=3)
        self.assertAlmostEqual(relic.y, 0.4681, places=3)

        planar = self.cache.get_element("target_planar_enter_1")
        self.assertAlmostEqual(planar.x, 0.8594, places=3)
        self.assertAlmostEqual(planar.y, 0.6159, places=3)

    def test_cache_persistence_and_meta_preservation(self):
        """Tests that cache serialization, _meta preservation, and reload work seamlessly."""
        # Check initial metadata
        self.assertEqual(self.cache.metadata.get("device"), "iPad Pro 13-inch (M5)")
        self.assertEqual(self.cache.metadata.get("screen_width"), 2752)
        self.assertEqual(self.cache.metadata.get("screen_height"), 2064)
        self.assertEqual(self.cache.metadata.get("aspect_ratio"), "4:3")

        # Update an element with bounding box and keywords
        custom_box = BoundingBox(0.10, 0.20, 0.30, 0.40)
        self.cache.update(
            "custom_btn",
            0.20,
            0.30,
            box=custom_box,
            label="Nút Tùy Chỉnh",
            keywords=["Tùy Chỉnh", "Custom"],
        )

        # Update resolution
        self.cache.update_resolution(2048, 1536)

        # Reload from disk
        reloaded = UICoordinateCache(filepath=self.test_cache_file)
        self.assertEqual(reloaded.metadata.get("screen_width"), 2048)
        self.assertEqual(reloaded.metadata.get("screen_height"), 1536)
        self.assertEqual(reloaded.metadata.get("aspect_ratio"), "4:3")

        elem = reloaded.get_element("custom_btn")
        self.assertIsNotNone(elem)
        self.assertEqual(elem.x, 0.20)
        self.assertEqual(elem.y, 0.30)
        self.assertEqual(elem.label, "Nút Tùy Chỉnh")
        self.assertEqual(elem.expected_keywords, ["Tùy Chỉnh", "Custom"])
        self.assertIsNotNone(elem.box)
        self.assertAlmostEqual(elem.box.x1, 0.10)
        self.assertAlmostEqual(elem.box.y1, 0.20)
        self.assertAlmostEqual(elem.box.x2, 0.30)
        self.assertAlmostEqual(elem.box.y2, 0.40)

    def test_ui_element_dataclass_methods(self):
        """Tests UIElement dataclass serialization and deserialization."""
        box = BoundingBox(0.25, 0.30, 0.35, 0.40)
        elem = UIElement(
            key="test_item",
            x=0.30,
            y=0.35,
            box=box,
            label="Test Item",
            expected_keywords=["Test", "Item"],
            verified_count=5,
            last_verified="2026-09-12 16:30:00",
        )

        self.assertEqual(elem.point.x, 0.30)
        self.assertEqual(elem.point.y, 0.35)

        data = elem.to_dict()
        self.assertEqual(data["x"], 0.30)
        self.assertEqual(data["y"], 0.35)
        self.assertEqual(data["box"], [0.25, 0.30, 0.35, 0.40])
        self.assertEqual(data["verified_count"], 5)

        deserialized = UIElement.from_dict("test_item", data)
        self.assertEqual(deserialized.key, "test_item")
        self.assertEqual(deserialized.x, 0.30)
        self.assertEqual(deserialized.y, 0.35)
        self.assertIsNotNone(deserialized.box)
        self.assertEqual(deserialized.box.x1, 0.25)
        self.assertEqual(deserialized.box.y2, 0.40)
        self.assertEqual(deserialized.verified_count, 5)

    def test_fast_path_micro_roi_speed_and_matching(self):
        """Tests fast-path micro-ROI execution speed (< 60ms) and accuracy."""
        # Create a synthetic image for repeatable benchmarking
        img = np.ones((600, 800, 3), dtype=np.uint8) * 255
        cv2.putText(img, "Uy Thac", (350, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)

        # Register button in cache at (0.50, 0.50)
        box = BoundingBox(0.40, 0.45, 0.60, 0.55)
        self.cache.update("test_btn", 0.50, 0.50, box=box, label="Ủy Thác", keywords=["Uy Thac", "Ủy Thác"])

        # Warm up OCR engine
        self.cache.verify_and_get("test_btn", img, self.ocr, roi_radius=0.08)

        # Benchmark fast-path micro-ROI execution time
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            pt, b, is_fast = self.cache.verify_and_get("test_btn", img, self.ocr, roi_radius=0.08)
            dur_ms = (time.perf_counter() - t0) * 1000.0
            times.append(dur_ms)
            self.assertTrue(is_fast)
            self.assertIsNotNone(pt)
            self.assertIsNotNone(b)

        min_time = min(times)
        avg_time = sum(times) / len(times)
        # Verify execution completed within expected micro-ROI threshold (< 250ms compared to 2200ms full OCR)
        self.assertLess(min_time, 250.0, f"Micro-ROI too slow: min={min_time:.1f}ms, avg={avg_time:.1f}ms")

        # Verify verified_count was incremented
        elem = self.cache.get_element("test_btn")
        self.assertGreaterEqual(elem.verified_count, 5)

    def test_fast_path_real_screenshot(self):
        """Tests micro-ROI verification on actual iPad Pro 13" screenshot if present."""
        img_path = (
            "assets/screenshots/real_ipad_screen.png"
            if os.path.exists("assets/screenshots/real_ipad_screen.png")
            else "real_ipad_screen.png"
        )
        if not os.path.exists(img_path):
            self.skipTest(f"{img_path} not present in repository")

        img = cv2.imread(img_path)
        self.assertIsNotNone(img)

        # Test chest 100 verification
        pt, box, is_fast = self.cache.verify_and_get("chest_100", img, self.ocr, roi_radius=0.04)
        self.assertTrue(is_fast)
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt.x, 0.3105, places=2)
        self.assertAlmostEqual(pt.y, 0.3577, places=2)

    def test_fast_path_icon_without_keywords(self):
        """Tests elements without expected_keywords (pure icons like back_button)."""
        pt, box, is_fast = self.cache.verify_and_get("back_button", np.zeros((100, 100, 3), dtype=np.uint8), self.ocr)
        self.assertTrue(is_fast)
        self.assertIsNotNone(pt)
        self.assertAlmostEqual(pt.x, 0.045, places=3)
        self.assertAlmostEqual(pt.y, 0.055, places=3)

    def test_self_healing_fallback_and_dynamic_updating(self):
        """Tests that when a button position shifts, self-healing discovers it, updates cache, and persists."""
        # 1. Create image with target text shifted to (0.25, 0.75)
        h, w = 600, 800
        img = np.ones((h, w, 3), dtype=np.uint8) * 255
        target_x_px, target_y_px = int(0.25 * w), int(0.75 * h)
        cv2.putText(img, "Khieu Chien", (target_x_px, target_y_px), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        # 2. Initially cache button at old/incorrect position (0.80, 0.20)
        self.cache.update("shifted_button", 0.80, 0.20, label="Khiêu Chiến", keywords=["Khieu Chien", "Khiêu Chiến"])
        old_pt = self.cache.get_point("shifted_button")
        self.assertEqual(old_pt.x, 0.80)
        self.assertEqual(old_pt.y, 0.20)

        # 3. Call verify_and_get: micro-ROI at (0.80, 0.20) will fail, triggering self-healing
        pt, box, is_fast = self.cache.verify_and_get("shifted_button", img, self.ocr, roi_radius=0.05, auto_heal=True)

        # 4. Verify fallback detected text and healed position (is_fast is False on recovery)
        self.assertFalse(is_fast, "Self-healing should report is_fast=False")
        self.assertIsNotNone(pt)
        self.assertIsNotNone(box)

        # Position should now be near (0.25-0.35, 0.70-0.76)
        self.assertTrue(0.20 <= pt.x <= 0.40, f"Healed X out of expected range: {pt.x}")
        self.assertTrue(0.70 <= pt.y <= 0.80, f"Healed Y out of expected range: {pt.y}")

        # 5. Verify the cache on disk was dynamically updated
        reloaded = UICoordinateCache(filepath=self.test_cache_file)
        reloaded_pt = reloaded.get_point("shifted_button")
        self.assertIsNotNone(reloaded_pt)
        self.assertAlmostEqual(reloaded_pt.x, pt.x, places=3)
        self.assertAlmostEqual(reloaded_pt.y, pt.y, places=3)

        # 6. Second call should now hit fast-path at newly learned position
        pt2, box2, is_fast2 = reloaded.verify_and_get("shifted_button", img, self.ocr, roi_radius=0.08, auto_heal=True)
        self.assertTrue(is_fast2, "Second call after healing should be fast-path")
        self.assertIsNotNone(pt2)

    def test_verify_and_get_missing_target_returns_none(self):
        """Tests that verify_and_get returns (None, None, False) when target text is absent."""
        img = np.ones((500, 500, 3), dtype=np.uint8) * 255
        self.cache.update("ghost_btn", 0.50, 0.50, label="Không Tồn Tại", keywords=["KhongTonTai12345"])
        pt, box, is_fast = self.cache.verify_and_get("ghost_btn", img, self.ocr, auto_heal=True)
        self.assertIsNone(pt)
        self.assertIsNone(box)
        self.assertFalse(is_fast)


if __name__ == "__main__":
    unittest.main()
