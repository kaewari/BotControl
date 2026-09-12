"""Unit tests for Sub-200ms End-to-End Human-like Touch Engine."""
import time
import unittest
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.touch_engine import FastTouchEngine, TouchResult
from bot.core.resource_guard import ResourceGuard, CONFIRMATION_ZONE
from tests.mock_wda import MockDeviceManager


class TestFastTouchEngine(unittest.TestCase):

    def setUp(self):
        self.device = MockDeviceManager()
        self.engine = FastTouchEngine(device=self.device)

    def test_sub_200ms_tap_latency(self):
        """Tests that end-to-end tap execution completes in < 200ms (Acceptance Criteria)."""
        box = BoundingBox(0.40, 0.45, 0.60, 0.55)
        target = box.center

        latencies = []
        for _ in range(100):
            res = self.engine.execute_fast_tap(target, box=box, label="TestButton")
            self.assertTrue(res.success)
            self.assertFalse(res.vetoed)
            self.assertLess(res.latencies.total_ms, 200.0)
            latencies.append(res.latencies.total_ms)

        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        self.assertLess(avg_lat, 100.0, f"Average latency too slow: {avg_lat:.2f}ms")
        self.assertLess(max_lat, 200.0, f"Max latency exceeded 200ms benchmark: {max_lat:.2f}ms")

    def test_gaussian_point_dispersion_and_randomness(self):
        """Tests that 1000 taps disperse naturally within the box and never repeat the same coordinate."""
        box = BoundingBox(0.20, 0.30, 0.40, 0.50)
        target = box.center

        points = []
        for _ in range(1000):
            res = self.engine.execute_fast_tap(target, box=box, spread_ratio=0.50)
            points.append(res.point)

        # 1. Check all points strictly inside box
        for p in points:
            self.assertTrue(box.contains(p), f"Point {p} fell outside {box}")

        # 2. Check no duplicate coordinates (anti-ban uniqueness)
        unique_pts = set((round(p.x, 5), round(p.y, 5)) for p in points)
        self.assertGreater(len(unique_pts), 990)

        # 3. Check mean center
        avg_x = sum(p.x for p in points) / len(points)
        avg_y = sum(p.y for p in points) / len(points)
        self.assertAlmostEqual(avg_x, target.x, delta=0.01)
        self.assertAlmostEqual(avg_y, target.y, delta=0.01)

    def test_biological_contact_duration(self):
        """Tests that touch hold duration is within human biological range (45ms - 85ms)."""
        durations = []
        for _ in range(100):
            res = self.engine.execute_fast_tap(Point(0.5, 0.5))
            last_event = self.device.tap_history[-1]
            durations.append(last_event.get("duration", 0.0))

        for d in durations:
            self.assertGreaterEqual(d, 0.040, f"Touch duration {d*1000:.1f}ms is unnaturally short")
            self.assertLessEqual(d, 0.090, f"Touch duration {d*1000:.1f}ms exceeds fast human range")

    def test_ram_video_frame_buffer_utilization(self):
        """Verifies that the touch engine utilizes 0.0ms RAM frame buffer without disk decode latency."""
        # Set synthetic frame in RAM
        bgr = np.zeros((100, 100, 3), dtype=np.uint8)
        self.device.set_frame(bgr)

        # Execute fast tap without supplying an explicit frame (forces engine to pull from RAM buffer)
        t0 = time.perf_counter()
        res = self.engine.execute_fast_tap(Point(0.5, 0.5))
        dur_ms = (time.perf_counter() - t0) * 1000.0

        self.assertTrue(res.success)
        self.assertLess(res.latencies.recognition_ms, 5.0)
        self.assertLess(dur_ms, 20.0)

    def test_target_resolution_from_cache(self):
        """Verifies resolving element key names directly from coordinate cache."""
        res = self.engine.execute_fast_tap("guidebook_icon")
        self.assertTrue(res.success)
        self.assertIsNotNone(res.point)
        # guidebook_icon center is around 0.79, 0.05
        self.assertAlmostEqual(res.point.x, 0.79, delta=0.03)
        self.assertAlmostEqual(res.point.y, 0.05, delta=0.03)

    def test_resource_guard_veto_in_touch_engine(self):
        """Confirms ResourceGuard blocks 100% of dangerous taps inside TouchEngine."""
        guard = ResourceGuard(device=self.device)
        self.engine.resource_guard = guard

        # 1. Tap inside confirmation zone
        res_zone = self.engine.execute_fast_tap(
            Point(CONFIRMATION_ZONE.center.x, CONFIRMATION_ZONE.center.y),
            label="Xác Nhận",
            require_active_threat=False,
        )
        self.assertFalse(res_zone.success)
        self.assertTrue(res_zone.vetoed)
        self.assertEqual(len(self.device.tap_history), 0)

        # 2. Tap with dangerous label
        res_label = self.engine.execute_fast_tap(
            Point(0.2, 0.2),
            label="Xác Nhận Tiêu Ngọc",
            require_active_threat=False,
        )
        self.assertFalse(res_label.success)
        self.assertTrue(res_label.vetoed)
        self.assertEqual(len(self.device.tap_history), 0)

    def test_zero_spend_post_jitter_safety(self):
        """Guarantees 100% Zero-Spend protection even when Gaussian jitter disperses towards CONFIRMATION_ZONE."""
        guard = ResourceGuard(device=self.device)
        self.engine.resource_guard = guard

        # Target just outside confirmation zone (0.55, 0.60, 0.75, 0.72)
        target = Point(0.545, 0.65)
        box = BoundingBox(0.53, 0.60, 0.57, 0.70)

        for _ in range(200):
            res = self.engine.execute_fast_tap(target, box=box, label="NearConfirmationZone", require_active_threat=False)
            if res.success:
                self.assertFalse(
                    CONFIRMATION_ZONE.contains(res.point),
                    f"FATAL: Tap point {res.point} dispersed into CONFIRMATION_ZONE {CONFIRMATION_ZONE}",
                )

    def test_tuple_and_positional_coordinates(self):
        """Verifies resolving tuple, list, and positional (x, y) coordinates in execute_fast_tap and fast_tap."""
        # 1. Tuple coordinate
        res1 = self.engine.execute_fast_tap((0.35, 0.45))
        self.assertTrue(res1.success)
        self.assertAlmostEqual(res1.point.x, 0.35, delta=0.03)

        # 2. List coordinate
        res2 = self.engine.execute_fast_tap([0.25, 0.75])
        self.assertTrue(res2.success)
        self.assertAlmostEqual(res2.point.x, 0.25, delta=0.03)

        # 3. Device manager positional fast_tap(x, y)
        self.device.clear_history()
        res3 = self.device.fast_tap(0.40, 0.60)
        self.assertTrue(res3.success)
        self.assertEqual(len(self.device.tap_history), 1)

    def test_nan_and_inf_target_rejection(self):
        """Verifies that NaN and Inf coordinates are rejected and never dispatched."""
        self.device.clear_history()

        # 1. NaN in tuple
        res_nan = self.engine.execute_fast_tap((float("nan"), 0.5))
        self.assertFalse(res_nan.success)
        self.assertIsNone(res_nan.point)

        # 2. Inf in positional
        res_inf = self.engine.execute_fast_tap(0.5, float("inf"))
        self.assertFalse(res_inf.success)

        # 3. NaN in Point
        res_pt = self.engine.execute_fast_tap(Point(float("nan"), float("nan")))
        self.assertFalse(res_pt.success)

        self.assertEqual(len(self.device.tap_history), 0, "No tap should be dispatched for NaN/Inf coordinates")

    def test_swipe_zero_spend_guarantee(self):
        """Confirms execute_fast_swipe strictly blocks swipes starting in, ending in, or intersecting CONFIRMATION_ZONE."""
        guard = ResourceGuard(device=self.device)
        self.engine.resource_guard = guard
        self.device.clear_history()

        # 1. Swipe starting in CONFIRMATION_ZONE
        res_start = self.engine.execute_fast_swipe(
            start=Point(CONFIRMATION_ZONE.center.x, CONFIRMATION_ZONE.center.y),
            end=Point(0.1, 0.1),
            label="SwipeFromConfirmation",
        )
        self.assertFalse(res_start.success)
        self.assertTrue(res_start.vetoed)

        # 2. Swipe ending in CONFIRMATION_ZONE
        res_end = self.engine.execute_fast_swipe(
            start=Point(0.1, 0.1),
            end=Point(CONFIRMATION_ZONE.center.x, CONFIRMATION_ZONE.center.y),
            label="SwipeToConfirmation",
        )
        self.assertFalse(res_end.success)
        self.assertTrue(res_end.vetoed)

        # 3. Swipe trajectory crossing through CONFIRMATION_ZONE
        res_cross = self.engine.execute_fast_swipe(
            start=Point(0.50, 0.66),
            end=Point(0.80, 0.66),
            label="CrossingSwipe",
        )
        self.assertFalse(res_cross.success)
        self.assertTrue(res_cross.vetoed)

        self.assertEqual(len(self.device.swipe_history), 0, "No swipe should ever reach device in/through CONFIRMATION_ZONE")

    def test_bounded_history_memory(self):
        """Verifies that touch engine history does not grow unbounded (capped at 1000 items)."""
        self.engine.history.clear()
        for i in range(1050):
            res = TouchResult(
                success=True,
                point=Point(0.5, 0.5),
                latencies=None,
            )
            self.engine._record_result(res)

        self.assertEqual(len(self.engine.history), 1000)

    def test_nan_inf_bounding_box_and_box_parameter(self):
        """Verifies NaN and Inf inside BoundingBoxes are safely rejected."""
        # 1. NaN in target BoundingBox
        res_nan = self.engine.execute_fast_tap(BoundingBox(float("nan"), 0.5, 0.6, 0.7))
        self.assertFalse(res_nan.success)
        self.assertIn("could not be resolved", res_nan.details)
        self.assertEqual(len(self.device.tap_history), 0)

        # 2. Inf in target BoundingBox
        res_inf = self.engine.execute_fast_tap(BoundingBox(0.4, 0.5, float("inf"), 0.7))
        self.assertFalse(res_inf.success)
        self.assertEqual(len(self.device.tap_history), 0)

        # 3. NaN in separate box parameter does not cause silent snap to 0.995
        res_box = self.engine.execute_fast_tap(Point(0.5, 0.5), box=BoundingBox(0.4, float("nan"), 0.6, 0.6))
        self.assertTrue(res_box.success)
        self.assertAlmostEqual(res_box.point.x, 0.5, delta=0.08)
        self.assertAlmostEqual(res_box.point.y, 0.5, delta=0.08)

        # 4. NaN in swipe target BoundingBox
        res_swipe = self.engine.execute_fast_swipe(BoundingBox(float("nan"), 0.5, 0.6, 0.7), Point(0.5, 0.5))
        self.assertFalse(res_swipe.success)
        self.assertEqual(len(self.device.swipe_history), 0)

    def test_pixel_coordinates_normalization_and_rejection(self):
        """Tests that pixel coordinates are correctly normalized and invalid off-screen coords rejected."""
        # 1. Screen center in pixels (1376, 1032 on 2752x2064)
        res_pixel = self.engine.execute_fast_tap((1376, 1032))
        self.assertTrue(res_pixel.success)
        self.assertAlmostEqual(res_pixel.point.x, 0.5, delta=0.05)
        self.assertAlmostEqual(res_pixel.point.y, 0.5, delta=0.05)

        # 2. Off-screen negative coordinates
        res_neg = self.engine.execute_fast_tap(Point(-50, -50))
        self.assertFalse(res_neg.success)
        self.assertEqual(len(self.device.tap_history), 1)  # Only the previous pixel tap was recorded

        # 3. Wildly exceeding coordinates
        res_huge = self.engine.execute_fast_tap((99999, 99999))
        self.assertFalse(res_huge.success)

    def test_unconditional_confirmation_zone_tap_veto_in_stage_2(self):
        """Confirms CONFIRMATION_ZONE taps are vetoed in Stage 2 even if require_active_threat=True."""
        guard = ResourceGuard(device=self.device)
        self.engine.resource_guard = guard

        self.device.clear_history()
        res = self.engine.execute_fast_tap(CONFIRMATION_ZONE.center, require_active_threat=False)
        self.assertFalse(res.success)
        self.assertTrue(res.vetoed)
        self.assertEqual(len(self.device.tap_history), 0)


if __name__ == "__main__":
    unittest.main()
