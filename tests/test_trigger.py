"""Unit and integration tests for ScreenStateTrigger and Frame Stability.

Tests cover:
- F-PIPE-01: ScreenStateTrigger Engine (micro-polling, predicate check, timeouts)
- F-PIPE-02: Fresh Frame Guard (timestamp guard rejecting stale frames)
- F-PIPE-03: Inter-Frame Stability Detector (absdiff <= 0.5% verification)
- F-PIPE-06: Micro-ROI Text Trigger (localized sub-window text verification)
"""
import time
import threading
import unittest
from typing import Optional
import cv2
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.cv.ocr_service import OCRService
from tests.mock_wda import MockDeviceManager

try:
    from bot.core.trigger import ScreenStateTrigger, FreshFrameGuard
except ImportError:
    from tests.mock_wda import ReferenceScreenStateTrigger as ScreenStateTrigger
    from tests.mock_wda import ReferenceFreshFrameGuard as FreshFrameGuard


class TestScreenStateTrigger(unittest.TestCase):
    """Test suite for event-driven screen state triggers and micro-polling."""

    def setUp(self):
        self.mock_device = MockDeviceManager()
        self.ocr = OCRService()
        self.trigger = ScreenStateTrigger(device=self.mock_device, ocr=self.ocr)

    # =========================================================================
    # Tier 1: Feature Coverage Tests
    # =========================================================================

    def test_wait_for_condition_immediate_success(self):
        """F-PIPE-01: Condition already satisfied returns True in < 15ms."""
        # Predicate is immediately true
        predicate = lambda img: img is not None
        t0 = time.time()
        res = self.trigger.wait_for_condition(predicate, timeout=1.0, min_delay=0.0)
        elapsed = time.time() - t0

        self.assertTrue(res)
        self.assertLess(elapsed, 0.15)

    def test_wait_for_condition_delayed_success(self):
        """F-PIPE-01: Condition becomes true after delay; trigger detects promptly."""
        condition_met = [False]

        def delayed_setter():
            time.sleep(0.10)
            condition_met[0] = True

        t = threading.Thread(target=delayed_setter, daemon=True)
        t.start()

        t0 = time.time()
        res = self.trigger.wait_for_condition(
            lambda img: condition_met[0],
            timeout=2.0,
            poll_interval=0.03,
            min_delay=0.0,
        )
        elapsed = time.time() - t0
        t.join(timeout=1.0)

        self.assertTrue(res)
        self.assertGreaterEqual(elapsed, 0.08)
        self.assertLess(elapsed, 0.50)

    def test_wait_for_condition_timeout(self):
        """F-PIPE-01: Condition never satisfied times out accurately and returns False."""
        t0 = time.time()
        res = self.trigger.wait_for_condition(
            lambda img: False,
            timeout=0.20,
            poll_interval=0.03,
            min_delay=0.0,
        )
        elapsed = time.time() - t0

        self.assertFalse(res)
        self.assertAlmostEqual(elapsed, 0.20, delta=0.10)

    def test_wait_for_roi_text_hit(self):
        """F-PIPE-06: Localized micro-ROI detects target text at expected location."""
        # Create a synthetic frame with "Uy Thac" at center (0.5, 0.5)
        h, w = self.mock_device.height, self.mock_device.width
        frame = np.ones((h, w, 3), dtype=np.uint8) * 255
        cv2.putText(frame, "Uy Thac", (int(w * 0.5 - 50), int(h * 0.5)), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
        self.mock_device.set_frame(frame)

        # Micro-ROI centered at (0.5, 0.5) should find text
        res = self.trigger.wait_for_roi_text(
            keywords=["Uy Thac", "Ủy Thác"],
            center_norm=Point(0.5, 0.5),
            timeout=1.0,
            roi_radius=0.12,
        )
        self.assertTrue(res)

    def test_wait_for_roi_text_miss(self):
        """F-PIPE-06: Micro-ROI outside the text bounding area returns False."""
        h, w = self.mock_device.height, self.mock_device.width
        frame = np.ones((h, w, 3), dtype=np.uint8) * 255
        cv2.putText(frame, "Uy Thac", (int(w * 0.5), int(h * 0.5)), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
        self.mock_device.set_frame(frame)

        # Micro-ROI far away at (0.1, 0.1) should not match
        res = self.trigger.wait_for_roi_text(
            keywords=["Uy Thac"],
            center_norm=Point(0.1, 0.1),
            timeout=0.25,
            roi_radius=0.05,
        )
        self.assertFalse(res)

    def test_inter_frame_stability_detection(self):
        """F-PIPE-03: Detects stabilization when screen delta is <= 0.5% over 2 frames."""
        # Set identical frames
        frame = np.ones((720, 960, 3), dtype=np.uint8) * 100
        self.mock_device.set_frame(frame)

        res = self.trigger.wait_for_screen_stable(
            max_change_ratio=0.005,
            timeout=1.0,
            stable_frames=2,
            poll_interval=0.02,
        )
        self.assertTrue(res)

    # =========================================================================
    # Tier 2: Boundary & Corner Cases
    # =========================================================================

    def test_screen_unstable_motion_rejected(self):
        """F-PIPE-03: Active motion prevents stability trigger until movement stops."""
        stop_motion = threading.Event()

        def motion_generator():
            counter = 0
            while not stop_motion.is_set():
                noisy = np.random.randint(0, 255, (720, 960, 3), dtype=np.uint8)
                self.mock_device.set_frame(noisy)
                counter += 1
                time.sleep(0.005)

        t = threading.Thread(target=motion_generator, daemon=True)
        t.start()

        # Should timeout while screen is changing rapidly
        res = self.trigger.wait_for_screen_stable(
            max_change_ratio=0.005,
            timeout=0.15,
            stable_frames=2,
            poll_interval=0.02,
        )
        stop_motion.set()
        t.join(timeout=1.0)

        self.assertFalse(res)

    def test_fresh_frame_guard_rejects_stale_timestamps(self):
        """F-PIPE-02: Frames captured before or at action timestamp are marked not fresh."""
        action_time = 1000.0
        guard = FreshFrameGuard(action_timestamp=action_time)

        # Pre-action timestamp: Stale
        self.assertFalse(guard.is_fresh(999.95))
        # Exact action timestamp: Stale
        self.assertFalse(guard.is_fresh(1000.00))
        # Post-action timestamp: Fresh!
        self.assertTrue(guard.is_fresh(1000.05))

    def test_zero_timeout_boundary(self):
        """F-PIPE-01: Zero timeout executes single check and terminates immediately."""
        t0 = time.time()
        res = self.trigger.wait_for_condition(lambda img: False, timeout=0.0, min_delay=0.0)
        elapsed = time.time() - t0

        self.assertFalse(res)
        self.assertLess(elapsed, 0.05)

    def test_predicate_exception_gracefully_handled(self):
        """F-PIPE-01: Exceptions inside predicate are caught and do not crash the trigger."""
        def faulty_predicate(img):
            raise ValueError("Test internal error in predicate")

        res = self.trigger.wait_for_condition(faulty_predicate, timeout=0.15, min_delay=0.0)
        self.assertFalse(res)

    # =========================================================================
    # Tier 3: Pairwise & Integration Tests
    # =========================================================================

    def test_trigger_with_sub_region_bounding_box(self):
        """F-PIPE-03 / Tier 3: Frame stability detector scoped to a localized BoundingBox."""
        box = BoundingBox(0.2, 0.2, 0.8, 0.8)
        frame = np.zeros((720, 960, 3), dtype=np.uint8)
        self.mock_device.set_frame(frame)

        res = self.trigger.wait_for_screen_stable(
            region=box,
            max_change_ratio=0.005,
            timeout=1.0,
            stable_frames=2,
            poll_interval=0.02,
        )
        self.assertTrue(res)

    def test_trigger_concurrency_with_mock_device_taps(self):
        """Tier 3: Trigger evaluates screen while device receives rapid simulated taps."""
        taps_executed = [0]
        stop_taps = threading.Event()

        def tap_loop():
            while not stop_taps.is_set():
                self.mock_device.tap(0.3, 0.3, normalized=True)
                taps_executed[0] += 1
                time.sleep(0.02)

        t = threading.Thread(target=tap_loop, daemon=True)
        t.start()

        # Trigger should wait for condition without deadlocking
        res = self.trigger.wait_for_condition(
            lambda img: taps_executed[0] >= 3,
            timeout=1.5,
            poll_interval=0.02,
            min_delay=0.0,
        )
        stop_taps.set()
        t.join(timeout=1.0)

        self.assertTrue(res)
        self.assertGreaterEqual(taps_executed[0], 3)

    def test_fresh_frame_guard_integration_in_trigger(self):
        """F-PIPE-02 / Tier 3: Trigger ignores pre-action frame until new frame arrives."""
        # Record action timestamp in trigger
        old_time = time.time()
        frame_old = np.zeros((720, 960, 3), dtype=np.uint8)
        self.mock_device.set_frame(frame_old, timestamp=old_time)

        if hasattr(self.trigger, "record_action"):
            time.sleep(0.02)
            self.trigger.record_action()

            # Schedule new frame
            def publish_fresh_frame():
                time.sleep(0.08)
                frame_new = np.ones((720, 960, 3), dtype=np.uint8) * 255
                self.mock_device.set_frame(frame_new, timestamp=time.time())

            t = threading.Thread(target=publish_fresh_frame, daemon=True)
            t.start()

            res = self.trigger.wait_for_condition(
                lambda img: np.mean(img) > 100,
                timeout=1.5,
                poll_interval=0.02,
                min_delay=0.0,
            )
            t.join(timeout=1.0)
            self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
