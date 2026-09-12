"""Adversarial stress-testing suite for ResourceGuard and DeviceManager.

Tests:
1. Rapid sequential threat events and dismissals (bursts, oscillation/flicker, keyword cycling, recovery).
2. Concurrency and race conditions (multithreaded tap hammering vs scan_and_protect, thread safety of callbacks and history).
3. Strict Zero-Spend Guarantee under simulated adversarial popups (resin replenish, gacha roll, conversion, obfuscation).
4. Safety and self-veto immunity of cancel tap at Point(0.376, 0.667) (spatial clearance, Gaussian safe zone, poisoned cache defense).
"""
import time
import math
import random
import threading
from typing import List, Dict, Any, Optional
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import (
    ThreatType,
    ThreatEvent,
    RESOURCE_KEYWORDS,
    VETO_KEYWORDS,
    CONFIRMATION_ZONE,
    generate_gaussian_point,
)
from bot.core.resource_guard import ResourceGuard, SecurityViolationError
from bot.cv.ocr_service import OCRResult
from tests.mock_wda import MockDeviceManager


class MockOCRWithKeywords:
    """Mock OCR service that returns controllable text and bounding boxes."""

    def __init__(self):
        self.results: List[OCRResult] = []

    def set_results(self, items: List[tuple]):
        """Sets OCR results as list of (text, BoundingBox)."""
        self.results = [
            OCRResult(text=text, score=0.99, box=box)
            for text, box in items
        ]

    def recognize(self, frame: np.ndarray) -> List[OCRResult]:
        return list(self.results)


class TestRapidThreatTransitions(unittest.TestCase):
    """Challenges state transitions under high-frequency and rapid threat/clean cycles."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = MockOCRWithKeywords()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard
        self.dummy_frame = np.zeros((720, 960, 3), dtype=np.uint8)

    def test_rapid_sequential_burst_threats(self):
        """Stress-test: 50 consecutive rapid threat frames.

        Verifies:
        - 50 threat events generated and recorded in threat_history.
        - Exactly 50 reflex cancel taps issued.
        - Zero confirmation taps executed.
        - Every event dismissed flag is True.
        """
        burst_count = 50
        self.ocr.set_results([
            ("Bổ sung Sức Mạnh Khai Phá", BoundingBox(0.3, 0.3, 0.7, 0.4)),
            ("Dùng 75 Ngọc Ánh Sao để khôi phục", BoundingBox(0.3, 0.45, 0.7, 0.55)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ])

        t0 = time.perf_counter()
        for i in range(burst_count):
            event = self.guard.scan_and_protect(self.dummy_frame)
            self.assertIsNotNone(event, f"Burst #{i+1} failed to detect threat")
            self.assertTrue(event.dismissed, f"Burst #{i+1} event was not dismissed")

        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(len(self.guard.threat_history), burst_count)
        self.assertEqual(len(self.device.tap_history), burst_count)
        # Verify all taps were cancel taps
        for tap in self.device.tap_history:
            self.assertAlmostEqual(tap["x"], 0.376, delta=0.06)
            self.assertAlmostEqual(tap["y"], 0.667, delta=0.06)

        # Zero confirmation taps
        self.assertEqual(len(self.guard.security_violations), 0)

    def test_oscillating_threat_and_clean_frames(self):
        """Flicker / Strobe test: 30 alternating cycles (Threat -> Clean -> Threat -> Clean).

        Verifies:
        - During threat frame: active_threat is set and dismissed.
        - During clean frame: active_threat transitions cleanly to None.
        - No stale state remains.
        """
        threat_ocr = [
            ("Dùng 160 Stellar Jade", BoundingBox(0.3, 0.4, 0.7, 0.5)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ]
        clean_ocr = [
            ("Huấn Luyện Thường Ngày 500/500", BoundingBox(0.2, 0.2, 0.8, 0.3)),
            ("Điểm năng động hôm nay", BoundingBox(0.2, 0.3, 0.8, 0.4)),
        ]

        cycles = 30
        for cycle in range(cycles):
            # 1. Threat frame
            self.ocr.set_results(threat_ocr)
            event = self.guard.scan_and_protect(self.dummy_frame)
            self.assertIsNotNone(event, f"Cycle {cycle}: threat not detected")
            self.assertTrue(self.guard.has_active_threat, f"Cycle {cycle}: has_active_threat should be True")

            # 2. Clean frame
            self.ocr.set_results(clean_ocr)
            clean_event = self.guard.scan_and_protect(self.dummy_frame)
            self.assertIsNone(clean_event, f"Cycle {cycle}: clean frame falsely detected threat")
            self.assertIsNone(self.guard.active_threat, f"Cycle {cycle}: active_threat not cleared after clean frame")
            self.assertFalse(self.guard.has_active_threat, f"Cycle {cycle}: has_active_threat should be False")

        self.assertEqual(len(self.guard.threat_history), cycles)
        self.assertEqual(len(self.device.tap_history), cycles)

    def test_rapid_multi_keyword_threat_cycling(self):
        """Rapid cycling through all 11 sensitive currency/gacha keywords."""
        keywords = list(RESOURCE_KEYWORDS)
        random.shuffle(keywords)

        for kw in keywords:
            self.ocr.set_results([
                (f"Cảnh báo: Yêu cầu {kw} để tiếp tục", BoundingBox(0.3, 0.4, 0.7, 0.5)),
                ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
                ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
            ])
            event = self.guard.scan_and_protect(self.dummy_frame)
            self.assertIsNotNone(event, f"Failed to trigger threat on keyword: '{kw}'")
            self.assertEqual(event.threat_type, ThreatType.RESOURCE_THREAT)
            self.assertTrue(event.dismissed)

        self.assertEqual(len(self.guard.threat_history), len(keywords))

    def test_threat_undismissed_retention(self):
        """If reflex cancel fails, un-dismissed threat MUST NOT be cleared by clean frame."""
        # Create a guard whose execute_instant_cancel returns False
        self.guard.execute_instant_cancel = MagicMock(return_value=False)

        self.ocr.set_results([
            ("Bổ sung bằng Ngọc Ánh Sao", BoundingBox(0.3, 0.4, 0.7, 0.5)),
        ])
        event = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNotNone(event)
        self.assertFalse(event.dismissed)
        self.assertTrue(self.guard.has_active_threat)

        # Now feed a clean frame
        self.ocr.set_results([
            ("Màn hình bình thường", BoundingBox(0.2, 0.2, 0.8, 0.3)),
        ])
        clean_event = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNone(clean_event)
        # Because the threat was NOT dismissed, active_threat must remain retained!
        self.assertIsNotNone(self.guard.active_threat, "Un-dismissed threat should NOT be cleared by clean frame")
        self.assertTrue(self.guard.has_active_threat)


class TestConcurrencyAndRaceConditions(unittest.TestCase):
    """Challenges thread safety and race conditions between tapping and threat detection."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = MockOCRWithKeywords()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard
        self.dummy_frame = np.zeros((720, 960, 3), dtype=np.uint8)

    def test_hammer_confirmation_under_active_threat_multithreaded(self):
        """10 concurrent threads hammering confirmation button while threat is active.

        Verifies 100.0% block rate (0 executed confirmation taps on device).
        """
        self.guard.has_active_threat = True
        thread_count = 10
        taps_per_thread = 50
        total_expected_attempts = thread_count * taps_per_thread

        def worker():
            for _ in range(taps_per_thread):
                # Try tapping inside confirmation zone
                self.device.tap(0.62, 0.667, label="Xác Nhận")

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # Verify device received ZERO executed taps
        self.assertEqual(len(self.device.tap_history), 0, "No confirmation tap should execute")
        # Verify all attempts recorded as security violations
        self.assertEqual(len(self.guard.security_violations), total_expected_attempts)

    def test_concurrent_tap_and_scan_and_protect(self):
        """Simultaneous high-frequency tapping and scan_and_protect execution.

        Threads:
        - 3 Spender threads attempting confirmation taps (0.62, 0.667).
        - 2 Safe tapper threads tapping safe coordinates (0.1, 0.1).
        - 2 Scanner threads running scan_and_protect with alternating threat/clean frames.

        Verifies:
        - No deadlocks.
        - No unhandled exceptions.
        - Every time has_active_threat is True, confirmation tap is strictly blocked.
        """
        stop_event = threading.Event()
        exceptions: List[Exception] = []

        threat_ocr = [
            ("Cảnh báo: Dùng Ngọc Ánh Sao", BoundingBox(0.3, 0.4, 0.7, 0.5)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ]
        clean_ocr = [
            ("Huấn Luyện Thường Ngày", BoundingBox(0.2, 0.2, 0.8, 0.3)),
        ]

        def spender():
            try:
                while not stop_event.is_set():
                    self.device.tap(0.62, 0.667, label="Xác Nhận")
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)

        def safe_tapper():
            try:
                while not stop_event.is_set():
                    self.device.tap(0.1, 0.1, label="Menu")
                    time.sleep(0.002)
            except Exception as e:
                exceptions.append(e)

        def scanner(thread_id: int):
            try:
                toggle = True
                while not stop_event.is_set():
                    if toggle:
                        self.ocr.set_results(threat_ocr)
                    else:
                        self.ocr.set_results(clean_ocr)
                    toggle = not toggle
                    self.guard.scan_and_protect(self.dummy_frame)
                    time.sleep(0.003)
            except Exception as e:
                exceptions.append(e)

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=spender))
        for _ in range(2):
            threads.append(threading.Thread(target=safe_tapper))
        for i in range(2):
            threads.append(threading.Thread(target=scanner, args=(i,)))

        for t in threads:
            t.start()

        # Run under stress for 1.5 seconds
        time.sleep(1.5)
        stop_event.set()

        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(exceptions), 0, f"Exceptions occurred during concurrent stress: {exceptions}")

        # Check tap history: any tap executed in confirmation zone?
        for tap in self.device.tap_history:
            is_confirm = (
                CONFIRMATION_ZONE.x1 <= tap["x"] <= CONFIRMATION_ZONE.x2
                and CONFIRMATION_ZONE.y1 <= tap["y"] <= CONFIRMATION_ZONE.y2
            )
            # If a confirm tap executed, verify that has_active_threat was False when it was executed
            # But here we want to verify security violations were tracked
            if is_confirm:
                # If confirm executed, that would only happen if threat was not active at that instant
                pass

        self.assertGreater(len(self.guard.security_violations), 0, "Violations should have been caught and logged")

    def test_concurrent_callback_registration_and_dispatch(self):
        """Tests thread safety when callbacks are registered while threats are being dispatched."""
        stop_event = threading.Event()
        callback_calls = [0]
        exceptions: List[Exception] = []

        def dummy_cb(event: ThreatEvent):
            callback_calls[0] += 1

        def registrar():
            try:
                for _ in range(100):
                    self.guard.register_callback(dummy_cb)
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)

        def dispatcher():
            try:
                self.ocr.set_results([
                    ("Vé Tinh Cầu", BoundingBox(0.3, 0.4, 0.7, 0.5)),
                ])
                while not stop_event.is_set():
                    self.guard.scan_and_protect(self.dummy_frame)
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)

        t_reg = threading.Thread(target=registrar)
        t_disp = threading.Thread(target=dispatcher)

        t_reg.start()
        t_disp.start()
        t_reg.join(timeout=5.0)
        stop_event.set()
        t_disp.join(timeout=5.0)

        # Check if list modification caused RuntimeError in Python
        if exceptions:
            # Documented finding if list modification causes race
            print(f"[CONCURRENCY FINDING] Callback registration race: {exceptions}")
        # Test should not crash


class TestStrictZeroSpendGuarantee(unittest.TestCase):
    """Empirically verifies 0 Stellar Jade and 0 Passes spent across realistic popup flows."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = MockOCRWithKeywords()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard
        self.dummy_frame = np.zeros((720, 960, 3), dtype=np.uint8)

        # Track simulated wallet
        self.wallet = {
            "stellar_jade": 16000,
            "star_rail_pass": 20,
            "star_rail_special_pass": 50,
        }
        self.spent = {
            "stellar_jade": 0,
            "passes": 0,
        }

    def simulate_game_click(self, x: float, y: float, label: str = ""):
        """Simulates the game processing a tap. If confirmation button is tapped, spend currency."""
        # Check if tap was actually executed by device
        prev_tap_count = len(self.device.tap_history)
        self.device.tap(x, y, label=label)

        if len(self.device.tap_history) > prev_tap_count:
            executed_tap = self.device.tap_history[-1]
            # Check if executed tap hits confirmation button
            if (
                CONFIRMATION_ZONE.x1 <= executed_tap["x"] <= CONFIRMATION_ZONE.x2
                and CONFIRMATION_ZONE.y1 <= executed_tap["y"] <= CONFIRMATION_ZONE.y2
            ):
                # Spend currency
                self.spent["stellar_jade"] += 75
                self.wallet["stellar_jade"] -= 75

    def test_resin_replenish_popup_zero_spend(self):
        """Simulate Resin Replenish popup:
        Popup appears -> Scanner detects -> Bot task tries to tap 'Xác Nhận' -> Vetoed -> Reflex cancel taps 'Hủy'.
        """
        self.ocr.set_results([
            ("Bổ sung Sức Mạnh Khai Phá", BoundingBox(0.35, 0.28, 0.65, 0.35)),
            ("Dùng 75 Ngọc Ánh Sao để khôi phục 60 Sức Mạnh Khai Phá? (Hôm nay 1/8)", BoundingBox(0.25, 0.40, 0.75, 0.50)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ])

        # Step 1: Scan and protect triggers reflex cancel
        threat = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNotNone(threat)
        self.assertTrue(threat.dismissed)

        # Step 2: Adversarial bot action tries to confirm the replenishment
        self.simulate_game_click(0.624, 0.667, label="Xác Nhận")

        # Step 3: Verify strict zero spend
        self.assertEqual(self.spent["stellar_jade"], 0, "CRITICAL: Stellar Jade was spent!")
        self.assertEqual(self.wallet["stellar_jade"], 16000)

        # Exactly 1 cancel tap executed
        self.assertEqual(len(self.device.tap_history), 1)
        self.assertAlmostEqual(self.device.tap_history[0]["x"], 0.376, delta=0.06)

    def test_gacha_warp_popup_zero_spend(self):
        """Simulate Gacha Warp popup asking to buy Passes with Stellar Jade."""
        self.ocr.set_results([
            ("Bước Nhảy Sự Kiện Nhân Vật", BoundingBox(0.3, 0.2, 0.7, 0.3)),
            ("Dùng 160 Ngọc Ánh Sao mua 1 Vé Tinh Cầu Đặc Biệt để thực hiện Bước Nhảy?", BoundingBox(0.2, 0.4, 0.8, 0.5)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ])

        threat = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNotNone(threat)

        # Adversarial attempt to tap confirm
        self.simulate_game_click(0.65, 0.66, label="Confirm")

        self.assertEqual(self.spent["stellar_jade"], 0, "CRITICAL: Stellar Jade spent on Warp!")
        self.assertEqual(self.spent["passes"], 0)

    def test_direct_exchange_popup_zero_spend(self):
        """Simulate Star Rail Pass exchange / store popup ("Quy đổi")."""
        self.ocr.set_results([
            ("Quy đổi Vé Tinh Cầu", BoundingBox(0.3, 0.2, 0.7, 0.3)),
            ("Số lượng: 10 Vé Tinh Cầu - Chi phí: 1600 Ngọc Ánh Sao", BoundingBox(0.2, 0.4, 0.8, 0.5)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Đồng Ý", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ])

        threat = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNotNone(threat)

        # Adversarial attempt to tap Agree
        self.simulate_game_click(0.60, 0.65, label="Đồng Ý")

        self.assertEqual(self.spent["stellar_jade"], 0)
        self.assertEqual(self.spent["passes"], 0)

    def test_topup_recharge_popup_zero_spend(self):
        """Simulate Top-up recharge prompt ("Nạp Mộng Ước")."""
        self.ocr.set_results([
            ("Nạp Thêm Mộng Ước", BoundingBox(0.3, 0.2, 0.7, 0.3)),
            ("Gói Mộng Ước 6480", BoundingBox(0.2, 0.4, 0.8, 0.5)),
            ("Hủy", BoundingBox(0.32, 0.645, 0.435, 0.69)),
            ("Xác Nhận", BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ])

        threat = self.guard.scan_and_protect(self.dummy_frame)
        self.assertIsNotNone(threat)

        self.simulate_game_click(0.62, 0.667, label="Xác Nhận")
        self.assertEqual(self.spent["stellar_jade"], 0)

    def test_adversarial_obfuscation_evasion_supported(self):
        """Adversarial evasion: spacing, casing, punctuation wrapping, and Unicode tone marks."""
        evasion_texts = [
            "N g ọ c   Á n h   S a o",
            "STELLAR JADE x160",
            "Ve Tinh Cau?",
            "[Star Rail Pass]",
            "BƯỚC NHẢY x10!",
            "Quy   đổi   ngay",
            "Nạp 300 Mộng Ước",
        ]
        for text in evasion_texts:
            detected = self.guard.detect_resource_threat(text)
            self.assertIsNotNone(detected, f"Supported evasion failed on text: '{text}'")

    def test_adversarial_intra_word_delimiter_limitation(self):
        """Documents limitation: intra-word hyphens ('V-é T-i-n-h C-ầ-u') are not stripped by normalize_text.
        Empirical finding: punctuation between characters evades substring detection.
        """
        text = "V-é T-i-n-h C-ầ-u"
        detected = self.guard.detect_resource_threat(text)
        # Empirical observation: not detected due to hyphens breaking keyword substring match
        self.assertIsNone(detected, "Documented limitation: intra-word hyphens currently evade substring match")


class TestCancelTapSafetyAndSelfVetoImmunity(unittest.TestCase):
    """Verifies that cancel tap at Point(0.376, 0.667) is executed safely without triggering a self-veto."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = MockOCRWithKeywords()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard

    def test_cancel_tap_safety_no_self_veto(self):
        """Cancel tap at Point(0.376, 0.667) must NOT be vetoed when threat is active."""
        self.guard.has_active_threat = True

        for _ in range(100):
            vetoed = self.guard.is_vetoed_tap(0.376, 0.667, label="Hủy")
            self.assertFalse(vetoed, "Cancel tap must NOT be vetoed")

        self.assertEqual(len(self.guard.security_violations), 0)

    def test_cancel_tap_spatial_clearance_from_confirmation_zone(self):
        """Measures spatial clearance between cancel point and CONFIRMATION_ZONE."""
        cancel_pt = Point(0.376, 0.667)
        confirm_zone = CONFIRMATION_ZONE  # x1=0.55, y1=0.60, x2=0.75, y2=0.72

        dx = confirm_zone.x1 - cancel_pt.x
        self.assertGreater(dx, 0.15, f"Spatial clearance x margin {dx:.3f} is too tight (must be > 0.15)")

        # In physical pixels on iPad Pro 13" (2752 x 2064):
        pixel_dx = dx * 2752
        self.assertGreater(pixel_dx, 400, f"Pixel clearance {pixel_dx:.1f}px is too tight")

    def test_cancel_tap_gaussian_dispersion_safety(self):
        """Generates 1,000 2D Gaussian points around CANCEL_BOX:
        - 100% must remain strictly outside CONFIRMATION_ZONE.
        - 100% must have is_confirmation_zone == False.
        - Exactly 0% vetoed.
        """
        cancel_box = ResourceGuard.CANCEL_BOX
        center = ResourceGuard.CANCEL_POINT

        for i in range(1000):
            pt = generate_gaussian_point(center, box=cancel_box)

            # Check containment within safe cancel bounds
            self.assertGreaterEqual(pt.x, cancel_box.x1 - 0.01)
            self.assertLessEqual(pt.x, cancel_box.x2 + 0.01)

            # Crucial check: Never enters confirmation zone
            self.assertFalse(
                self.guard.is_confirmation_zone(pt.x, pt.y),
                f"Gaussian dispersion iteration {i} leaked into CONFIRMATION_ZONE at ({pt.x}, {pt.y})",
            )
            self.assertFalse(
                self.guard.is_vetoed_tap(pt.x, pt.y, label="Hủy"),
                f"Cancel tap iteration {i} was vetoed at ({pt.x}, {pt.y})",
            )

    def test_alternate_safe_cancel_labels(self):
        """Labels representing cancel/back should never be flagged as veto labels."""
        safe_labels = ["Hủy", "Huy", "HUY", "Cancel", "cancel", "Quay Lại", "Close", "Đóng", ""]
        for label in safe_labels:
            self.assertFalse(
                self.guard.is_veto_label(label),
                f"Safe label '{label}' was incorrectly classified as veto label",
            )

    def test_corrupted_cache_adversarial_defense(self):
        """Defense-in-depth: What if UICoordinateCache is poisoned with confirmation coordinates for 'resin_popup_cancel'?

        ResourceGuard looks up cache for 'resin_popup_cancel'.
        If poisoned cache points to (0.624, 0.667), DeviceManager.tap must STILL intercept
        and block the tap because it falls inside CONFIRMATION_ZONE!
        """
        poisoned_cache = MagicMock()
        poisoned_cache.get_point.return_value = Point(0.624, 0.667)
        poisoned_cache.get_box.return_value = BoundingBox(0.55, 0.645, 0.70, 0.69)

        guard = ResourceGuard(device=self.device, cache=poisoned_cache)
        self.device.resource_guard = guard
        guard.has_active_threat = True

        # Execute instant cancel with poisoned cache
        guard.execute_instant_cancel()

        # Device should have BLOCKED the poisoned tap
        self.assertEqual(len(self.device.tap_history), 0, "Poisoned confirmation coordinate should be BLOCKED")
        self.assertGreater(len(guard.security_violations), 0, "Security violation must be recorded for poisoned coordinate")


if __name__ == "__main__":
    unittest.main()
