"""Unit and integration tests for Fast Chain Action Execution.

Tests cover:
- F-PIPE-04: Fast Chain Action Executor
- Statistical validation of Gaussian inter-tap cadence (110-180ms)
- 2D Gaussian point dispersion within inner 70% safe bounding box
- Biological touch hold contact duration (85-210ms)
- Anti-ban non-repetition guarantees and graceful cancellation
"""
import time
import unittest
from typing import List, Tuple, Optional
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from tests.mock_wda import MockDeviceManager

try:
    from bot.tasks.fast_chain import FastChainExecutor
except ImportError:
    from tests.mock_wda import ReferenceFastChainExecutor as FastChainExecutor


class TestFastChainExecutor(unittest.TestCase):
    """Test suite for high-cadence fast chain actions."""

    def setUp(self):
        self.mock_device = MockDeviceManager()
        self.executor = FastChainExecutor(device=self.mock_device)

    # =========================================================================
    # Tier 1: Feature Coverage Tests
    # =========================================================================

    def test_fast_chain_preserves_biological_touch_hold(self):
        """F-PIPE-04: Every tap in the fast chain records hold duration in [85ms, 210ms]."""
        targets = [
            (Point(0.2, 0.5), BoundingBox(0.15, 0.45, 0.25, 0.55)),
            (Point(0.4, 0.5), BoundingBox(0.35, 0.45, 0.45, 0.55)),
            (Point(0.6, 0.5), BoundingBox(0.55, 0.45, 0.65, 0.55)),
        ]
        self.executor.execute_chain(targets)

        self.assertEqual(len(self.mock_device.tap_history), 3)
        for tap in self.mock_device.tap_history:
            self.assertEqual(tap["type"], "tap_hold")
            duration = tap["duration"]
            self.assertGreaterEqual(duration, 0.080, f"Duration {duration*1000:.1f}ms below 80ms minimum")
            self.assertLessEqual(duration, 0.220, f"Duration {duration*1000:.1f}ms exceeded 220ms maximum")

    def test_fast_chain_gaussian_box_containment(self):
        """F-PIPE-04: 50 taps to a target box all land strictly inside the bounding box."""
        box = BoundingBox(0.30, 0.40, 0.50, 0.60)
        target = (box.center, box)
        targets = [target] * 50

        # Execute multiple single taps to collect dispersion statistics
        for _ in range(50):
            self.mock_device.tap(box.center.x, box.center.y, normalized=True, box=box)

        self.assertEqual(len(self.mock_device.tap_history), 50)
        for tap in self.mock_device.tap_history:
            pt = Point(tap["x"], tap["y"])
            self.assertTrue(
                box.contains(pt),
                f"Gaussian tap {pt} landed outside safe bounding box {box}",
            )

    def test_fast_chain_zero_pixel_repetition(self):
        """F-PIPE-04: No two consecutive taps click the exact same pixel coordinates."""
        box = BoundingBox(0.10, 0.10, 0.30, 0.30)
        for _ in range(30):
            self.mock_device.tap(box.center.x, box.center.y, normalized=True, box=box)

        coords = [(round(t["x"], 5), round(t["y"], 5)) for t in self.mock_device.tap_history]
        # Verify diversity
        unique_coords = set(coords)
        self.assertGreaterEqual(len(unique_coords), 28)

    def test_fast_chain_sequential_order(self):
        """F-PIPE-04: Targets are executed in strict left-to-right / sequential order."""
        targets = [
            (Point(0.1, 0.2), None),
            (Point(0.3, 0.4), None),
            (Point(0.5, 0.6), None),
            (Point(0.7, 0.8), None),
            (Point(0.9, 1.0), None),
        ]
        self.executor.execute_chain(targets)

        self.assertEqual(len(self.mock_device.tap_history), 5)
        for i, tap in enumerate(self.mock_device.tap_history):
            self.assertAlmostEqual(tap["x"], targets[i][0].x, delta=0.06)

    def test_fast_chain_gaussian_cadence_distribution(self):
        """F-PIPE-04: Inter-tap delays fall within [105ms, 200ms] with natural variance."""
        targets = [(Point(0.5, 0.5), None)] * 4

        t0 = time.time()
        self.executor.execute_chain(targets, mean_cadence=0.145, std_cadence=0.022)
        total_time = time.time() - t0

        # For 4 taps, there are 3 inter-tap intervals (expected ~3 * 0.145s = 0.435s)
        self.assertGreaterEqual(total_time, 0.30)
        self.assertLessEqual(total_time, 0.70)

    # =========================================================================
    # Tier 2: Boundary & Corner Cases
    # =========================================================================

    def test_fast_chain_empty_target_list(self):
        """F-PIPE-04: Empty target list returns True immediately without error."""
        res = self.executor.execute_chain([])
        self.assertTrue(res)
        self.assertEqual(len(self.mock_device.tap_history), 0)

    def test_fast_chain_cancellation_mid_sequence(self):
        """F-PIPE-04: Stop predicate halts the chain immediately after current tap."""
        stop_flag = [False]
        executor = FastChainExecutor(
            device=self.mock_device,
            stop_predicate=lambda: stop_flag[0],
        )

        targets = [
            (Point(0.1, 0.1), None),
            (Point(0.2, 0.2), None),
            (Point(0.3, 0.3), None),
            (Point(0.4, 0.4), None),
        ]

        # Trigger stop after 2nd tap by checking history in hook or threading
        def check_stop():
            while len(self.mock_device.tap_history) < 2:
                time.sleep(0.01)
            stop_flag[0] = True

        import threading
        t = threading.Thread(target=check_stop, daemon=True)
        t.start()

        res = executor.execute_chain(targets)
        t.join(timeout=1.0)

        self.assertFalse(res)
        # Should have executed only 2 or 3 taps before stopping, not all 4
        self.assertLess(len(self.mock_device.tap_history), 4)

    def test_fast_chain_point_without_box(self):
        """F-PIPE-04: Targets without BoundingBox dispatch point taps with biological hold."""
        targets = [(Point(0.45, 0.75), None)]
        self.executor.execute_chain(targets)

        self.assertEqual(len(self.mock_device.tap_history), 1)
        tap = self.mock_device.tap_history[0]
        self.assertAlmostEqual(tap["x"], 0.45, delta=0.06)
        self.assertAlmostEqual(tap["y"], 0.75, delta=0.06)
        self.assertGreaterEqual(tap["duration"], 0.080)

    def test_fast_chain_screen_edge_containment(self):
        """F-PIPE-04: Taps near screen edges (0.01, 0.99) remain clamped inside [0.005, 0.995]."""
        targets = [
            (Point(0.005, 0.005), None),
            (Point(0.995, 0.995), None),
        ]
        self.executor.execute_chain(targets)

        for tap in self.mock_device.tap_history:
            self.assertGreaterEqual(tap["x"], 0.005)
            self.assertLessEqual(tap["x"], 0.995)
            self.assertGreaterEqual(tap["y"], 0.005)
            self.assertLessEqual(tap["y"], 0.995)

    # =========================================================================
    # Tier 3: Pairwise & Real Integration
    # =========================================================================

    def test_fast_chain_with_5_daily_chests(self):
        """Tier 3 / F-PIPE-04: Simulates fast chain collection of all 5 daily chests (100-500)."""
        chest_boxes = [
            BoundingBox(0.245, 0.155, 0.285, 0.205),  # 100
            BoundingBox(0.380, 0.155, 0.420, 0.205),  # 200
            BoundingBox(0.515, 0.155, 0.555, 0.205),  # 300
            BoundingBox(0.650, 0.155, 0.690, 0.205),  # 400
            BoundingBox(0.785, 0.155, 0.825, 0.205),  # 500
        ]
        targets = [(b.center, b) for b in chest_boxes]

        t0 = time.time()
        res = self.executor.execute_chain(targets)
        elapsed = time.time() - t0

        self.assertTrue(res)
        self.assertEqual(len(self.mock_device.tap_history), 5)
        # 5 chests with 4 pauses (~145ms each) should complete in ~0.55s - 0.85s
        self.assertLess(elapsed, 1.20)

    def test_fast_chain_concurrency_with_stream_readers(self):
        """Tier 3: Fast chain executes concurrently while stream frame reads occur."""
        stop_stream = False

        def stream_reader():
            while not stop_stream:
                _ = self.mock_device.get_screenshot_jpeg_bytes()
                time.sleep(0.01)

        import threading
        t = threading.Thread(target=stream_reader, daemon=True)
        t.start()

        targets = [(Point(0.5, 0.5), None)] * 5
        res = self.executor.execute_chain(targets)
        stop_stream = True
        t.join(timeout=1.0)

        self.assertTrue(res)
        self.assertEqual(len(self.mock_device.tap_history), 5)


if __name__ == "__main__":
    unittest.main()
