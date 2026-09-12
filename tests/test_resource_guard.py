"""Unit and integration test suite for Zero-Spend ResourceGuard (Milestone M5).

Covers:
- F-GUARD-01: Detection of sensitive currency/gacha keywords (diacritics, unaccented, and English).
- F-GUARD-02: Sub-500ms reflex cancel tapping 'Hủy' at Point(0.376, 0.667).
- F-GUARD-03: Strict pre-tap veto preventing any tap on 'Xác Nhận' / 'Đồng Ý' or within CONFIRMATION_ZONE.
- Threat taxonomy & event definitions (ThreatType, ThreatEvent).
- DeviceManager / MockDeviceManager integration with 100% block rate on dangerous taps.
- Security violation audit logging and threat callback dispatch.
"""
import os
import time
import unittest
from unittest.mock import MagicMock
from typing import List, Optional
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import (
    ThreatType,
    ThreatEvent,
    RESOURCE_KEYWORDS,
    VETO_KEYWORDS,
    CONFIRMATION_ZONE,
)
from bot.core.resource_guard import ResourceGuard, SecurityViolationError
from bot.cv.ocr_service import OCRService
from tests.mock_wda import MockDeviceManager


def create_synthetic_frame_with_text(
    text: str,
    width: int = 1200,
    height: int = 800,
    pos: tuple = (300, 300),
    font_size: int = 36,
) -> np.ndarray:
    """Generates a clean synthetic RGB image with specified text."""
    img = Image.new("RGB", (width, height), color=(30, 32, 40))
    draw = ImageDraw.Draw(img)

    font = None
    for candidate in [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]:
        if os.path.exists(candidate):
            try:
                font = ImageFont.truetype(candidate, font_size)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    draw.text(pos, text, font=font, fill=(255, 255, 255))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


class TestResourceGuard(unittest.TestCase):
    """Initial baseline test suite for ResourceGuard zero-spend enforcement."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = MagicMock()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)

    def test_detect_sensitive_keywords(self):
        """F-GUARD-01: Verifies detection of Stellar Jade, Passes, and Warp keywords."""
        keywords_to_test = [
            "Bổ sung 60 Sức Mạnh Khai Phá bằng Ngọc Ánh Sao?",
            "Ngoc Anh Sao can de doi",
            "Purchase 160 Stellar Jade",
            "Dùng 1 Vé Tinh Cầu Đặc Biệt",
            "Ve Tinh Cau de quay",
            "Mở giao diện Bước Nhảy",
            "Warp x10 Banner",
        ]
        for text in keywords_to_test:
            detected = self.guard.detect_resource_threat(text)
            self.assertIsNotNone(
                detected,
                f"Failed to detect resource threat in: '{text}'",
            )

    def test_safe_texts_not_flagged(self):
        """Verifies normal gameplay text is not falsely flagged as a resource threat."""
        safe_texts = [
            "Huấn Luyện Thường Ngày",
            "Điểm năng động hôm nay: 500/500",
            "Ủy Thác hoàn thành",
            "Bắt đầu khiêu chiến",
            "Tự động chiến đấu",
            "Nhận Thưởng",
            "Thẩm Án Xâm Thực",
        ]
        for text in safe_texts:
            detected = self.guard.detect_resource_threat(text)
            self.assertIsNone(
                detected,
                f"False positive threat detected in safe text: '{text}'",
            )

    def test_sub_500ms_reflex_cancel(self):
        """F-GUARD-02: Verifies reflex cancel taps 'Hủy' at (0.376, 0.667) in < 0.5s."""
        self.ocr.recognize.return_value = [
            MagicMock(text="Bổ Sung Sức Mạnh Khai Phá", box=BoundingBox(0.3, 0.3, 0.7, 0.4)),
            MagicMock(text="Dùng 75 Ngọc Ánh Sao để khôi phục", box=BoundingBox(0.3, 0.45, 0.7, 0.55)),
            MagicMock(text="Hủy", box=BoundingBox(0.32, 0.645, 0.435, 0.69)),
            MagicMock(text="Xác Nhận", box=BoundingBox(0.55, 0.645, 0.70, 0.69)),
        ]

        dummy_img = np.zeros((720, 960, 3), dtype=np.uint8)

        t0 = time.time()
        handled = self.guard.evaluate_and_protect(dummy_img)
        elapsed = time.time() - t0

        self.assertTrue(handled, "ResourceGuard should handle and cancel popup")
        self.assertLess(elapsed, 0.50, f"Reflex cancel took {elapsed:.3f}s (must be < 0.5s)")

        self.assertGreater(len(self.device.tap_history), 0)
        last_tap = self.device.tap_history[-1]
        self.assertAlmostEqual(last_tap["x"], 0.376, delta=0.06)
        self.assertAlmostEqual(last_tap["y"], 0.667, delta=0.06)

    def test_strict_pre_tap_veto_confirmation_zone(self):
        """F-GUARD-03: Verifies pre-tap veto blocks tapping in CONFIRMATION_ZONE or on 'Xác Nhận'."""
        self.guard.has_active_threat = True

        with self.assertRaises(SecurityViolationError):
            self.guard.pre_tap_veto(0.624, 0.667, label="Xác Nhận")

        pixel_x = int(0.624 * 2752)
        pixel_y = int(0.667 * 2064)
        with self.assertRaises(SecurityViolationError):
            self.guard.pre_tap_veto(pixel_x, pixel_y, label="Confirm")

        self.assertGreater(len(self.guard.security_violations), 0)

    def test_safe_taps_allowed_outside_threat(self):
        """Verifies normal safe taps succeed when no threat is present."""
        self.guard.has_active_threat = False
        allowed = self.guard.pre_tap_veto(0.10, 0.20, label="Daily Training")
        self.assertTrue(allowed)

    def test_threat_callback_dispatch(self):
        """Verifies callbacks receive ThreatEvent when a threat is detected."""
        events_received = []
        self.guard.register_callback(lambda ev: events_received.append(ev))

        self.ocr.recognize.return_value = [
            MagicMock(text="Tiêu hao Ngọc Ánh Sao", box=BoundingBox(0.3, 0.4, 0.7, 0.5)),
        ]
        dummy_img = np.zeros((720, 960, 3), dtype=np.uint8)
        self.guard.evaluate_and_protect(dummy_img)

        self.assertEqual(len(events_received), 1)
        self.assertIn("Ngọc Ánh Sao", events_received[0].details)


class TestThreatTaxonomy(unittest.TestCase):
    """Verifies ThreatType enum, ThreatEvent dataclass, and required constants."""

    def test_threat_type_enum_values(self):
        self.assertEqual(ThreatType.FATAL_SECURITY.value, "fatal_security")
        self.assertEqual(ThreatType.RESOURCE_THREAT.value, "resource_threat")
        self.assertIsInstance(ThreatType.FATAL_SECURITY, str)
        self.assertIsInstance(ThreatType.RESOURCE_THREAT, str)

    def test_threat_event_dataclass_fields(self):
        bbox = BoundingBox(0.1, 0.2, 0.3, 0.4)
        event = ThreatEvent(
            threat_type=ThreatType.RESOURCE_THREAT,
            keyword="Ngọc Ánh Sao",
            timestamp=1700000000.0,
            bbox=bbox,
            dismissed=True,
            details="Test event details",
        )
        self.assertEqual(event.threat_type, ThreatType.RESOURCE_THREAT)
        self.assertEqual(event.keyword, "Ngọc Ánh Sao")
        self.assertEqual(event.timestamp, 1700000000.0)
        self.assertEqual(event.bbox, bbox)
        self.assertTrue(event.dismissed)
        self.assertEqual(event.details, "Test event details")

    def test_required_resource_keywords_present(self):
        expected = [
            "Ngọc Ánh Sao",
            "Ngoc Anh Sao",
            "Stellar Jade",
            "Vé Tinh Cầu",
            "Ve Tinh Cau",
            "Star Rail Pass",
            "Star Rail Special Pass",
            "Bước Nhảy",
            "Warp",
            "Quy đổi",
            "Nạp",
        ]
        for kw in expected:
            self.assertIn(kw, RESOURCE_KEYWORDS, f"Missing required keyword: {kw}")

    def test_required_veto_keywords_present(self):
        expected = ["Xác Nhận", "Xac Nhan", "Đồng Ý", "Dong Y", "Confirm", "Agree"]
        for kw in expected:
            self.assertIn(kw, VETO_KEYWORDS, f"Missing veto keyword: {kw}")

    def test_confirmation_zone_dimensions(self):
        self.assertEqual(CONFIRMATION_ZONE.x1, 0.55)
        self.assertEqual(CONFIRMATION_ZONE.y1, 0.60)
        self.assertEqual(CONFIRMATION_ZONE.x2, 0.75)
        self.assertEqual(CONFIRMATION_ZONE.y2, 0.72)


class TestKeywordDetectionComprehensive(unittest.TestCase):
    """Tests keyword detection across Vietnamese with diacritics, without diacritics, and English."""

    def setUp(self):
        self.guard = ResourceGuard()

    def test_all_11_resource_keywords_detected(self):
        test_cases = [
            ("Bổ sung bằng Ngọc Ánh Sao", "Ngọc Ánh Sao"),
            ("Su dung Ngoc Anh Sao", "Ngoc Anh Sao"),
            ("Requires 160 Stellar Jade", "Stellar Jade"),
            ("Nhận 1 Vé Tinh Cầu", "Vé Tinh Cầu"),
            ("Dung Ve Tinh Cau", "Ve Tinh Cau"),
            ("Dùng Star Rail Pass", "Star Rail Pass"),
            ("Dùng Star Rail Special Pass", "Star Rail Special Pass"),
            ("Mở Bước Nhảy nhân vật", "Bước Nhảy"),
            ("Open Warp screen", "Warp"),
            ("Quy đổi mộng ước", "Quy đổi"),
            ("Nạp tiền tài khoản", "Nạp"),
        ]
        for phrase, expected_kw in test_cases:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNotNone(detected, f"Failed to detect keyword '{expected_kw}' in: '{phrase}'")

    def test_veto_keywords_detection(self):
        veto_samples = [
            "Xác Nhận", "xác nhận", "Xac Nhan", "xac nhan",
            "Đồng Ý", "đồng ý", "Dong Y", "dong y",
            "Confirm", "confirm", "Agree", "agree",
        ]
        for label in veto_samples:
            self.assertTrue(self.guard.is_veto_label(label), f"Failed to identify veto label: '{label}'")

    def test_safe_labels_not_identified_as_veto(self):
        safe_labels = ["Hủy", "Huy", "HỦY BỎ", "Cancel", "Quay Lại", "Ủy Thác", "Menu", "Nhận"]
        for label in safe_labels:
            self.assertFalse(self.guard.is_veto_label(label), f"False positive veto label on: '{label}'")


class TestConfirmationZoneGeometry(unittest.TestCase):
    """Tests bounding box containment and coordinate conversion for CONFIRMATION_ZONE."""

    def setUp(self):
        self.guard = ResourceGuard()

    def test_points_inside_confirmation_zone(self):
        inside_points = [
            (0.62, 0.667),  # Standard resin popup confirm center
            (0.55, 0.60),   # Top-left corner
            (0.75, 0.72),   # Bottom-right corner
            (0.65, 0.65),   # Interior
            (0.56, 0.61),
            (0.74, 0.71),
        ]
        for x, y in inside_points:
            self.assertTrue(self.guard.is_confirmation_zone(x, y), f"Point ({x}, {y}) should be in confirmation zone")

    def test_points_outside_confirmation_zone(self):
        outside_points = [
            (0.376, 0.667),  # Cancel button
            (0.045, 0.055),  # Back button
            (0.963, 0.065),  # Close button
            (0.54, 0.65),    # Left of zone
            (0.76, 0.65),    # Right of zone
            (0.65, 0.59),    # Above zone
            (0.65, 0.73),    # Below zone
            (0.10, 0.10),
            (0.85, 0.85),
        ]
        for x, y in outside_points:
            self.assertFalse(self.guard.is_confirmation_zone(x, y), f"Point ({x}, {y}) should NOT be in confirmation zone")

    def test_pixel_coordinates_handling(self):
        device = MockDeviceManager(width=2752, height=2064)
        guard = ResourceGuard(device=device)

        # Inside pixel coordinates: norm (0.62, 0.667) -> px (1706.24, 1376.688)
        px_inside_x = 0.62 * 2752
        px_inside_y = 0.667 * 2064
        self.assertTrue(guard.is_confirmation_zone(px_inside_x, px_inside_y))

        # Outside pixel coordinates: norm (0.376, 0.667) -> px (1034.752, 1376.688)
        px_outside_x = 0.376 * 2752
        px_outside_y = 0.667 * 2064
        self.assertFalse(guard.is_confirmation_zone(px_outside_x, px_outside_y))


class TestStrictPreTapVetoDeep(unittest.TestCase):
    """Verifies that taps targeting confirmation zone or veto labels are blocked 100% of the time when threat is active."""

    def setUp(self):
        self.device = MockDeviceManager()
        self.guard = ResourceGuard(device=self.device)
        self.device.resource_guard = self.guard

    def test_veto_blocks_confirmation_zone_when_threat_active(self):
        self.guard.has_active_threat = True

        # Attempt to tap at confirm button location
        is_vetoed = self.guard.is_vetoed_tap(0.62, 0.667)
        self.assertTrue(is_vetoed)
        self.assertEqual(len(self.guard.security_violations), 1)
        self.assertIn("CONFIRMATION_ZONE", self.guard.security_violations[0]["detail"])

    def test_veto_blocks_veto_labels_when_threat_active(self):
        self.guard.has_active_threat = True

        for label in ["Xác Nhận", "Đồng Ý", "Confirm", "Agree", "Xac Nhan"]:
            is_vetoed = self.guard.is_vetoed_tap(0.1, 0.1, label=label)
            self.assertTrue(is_vetoed, f"Veto should block label '{label}'")

    def test_veto_allows_cancel_button_when_threat_active(self):
        self.guard.has_active_threat = True

        # Cancel button at (0.376, 0.667) with label "Hủy"
        is_vetoed = self.guard.is_vetoed_tap(0.376, 0.667, label="Hủy")
        self.assertFalse(is_vetoed, "Cancel tap must NOT be vetoed")

    def test_normal_taps_allowed_when_threat_inactive(self):
        self.guard.has_active_threat = False

        # No active threat: confirmation zone taps during normal gameplay must not be vetoed
        is_vetoed = self.guard.is_vetoed_tap(0.62, 0.667)
        self.assertFalse(is_vetoed, "Normal tap must not be blocked when no threat is active")

        is_vetoed_label = self.guard.is_vetoed_tap(0.1, 0.1, label="Xác Nhận")
        self.assertFalse(is_vetoed_label, "Normal label tap must not be blocked when no threat is active")

    def test_100_percent_block_rate_under_repeated_attempts(self):
        self.guard.has_active_threat = True
        total_attempts = 100
        blocked_count = 0

        for _ in range(total_attempts):
            if self.guard.is_vetoed_tap(0.62, 0.667):
                blocked_count += 1

        self.assertEqual(blocked_count, total_attempts, "Confirmation zone taps must be blocked 100% of the time")
        self.assertEqual(len(self.guard.security_violations), total_attempts)

    def test_unconditional_veto_candidate_check(self):
        self.guard.has_active_threat = False
        self.assertTrue(self.guard.is_vetoed_tap(0.62, 0.667, require_active_threat=False))
        self.assertTrue(self.guard.is_vetoed_tap(0.1, 0.1, label="Xác Nhận", require_active_threat=False))
        self.assertFalse(self.guard.is_vetoed_tap(0.376, 0.667, label="Hủy", require_active_threat=False))


class TestMockDeviceManagerPreTapHook(unittest.TestCase):
    """Verifies that MockDeviceManager intercepts vetoed taps before execution."""

    def setUp(self):
        self.device = MockDeviceManager()
        self.guard = ResourceGuard(device=self.device)
        self.device.resource_guard = self.guard

    def test_mock_device_tap_blocked_by_guard(self):
        self.guard.has_active_threat = True

        # Attempt to tap in confirmation zone
        self.device.tap(0.62, 0.667)
        self.assertEqual(len(self.device.tap_history), 0, "Tap in confirmation zone should be vetoed and not executed")

        # Attempt to tap with veto label
        self.device.tap(0.1, 0.1, label="Xác Nhận")
        self.assertEqual(len(self.device.tap_history), 0, "Tap with veto label should be vetoed and not executed")

        # Tap with safe cancel button should succeed
        self.device.tap(0.376, 0.667, label="Hủy")
        self.assertEqual(len(self.device.tap_history), 1, "Cancel tap should be executed")

    def test_mock_device_tap_hold_blocked_by_guard(self):
        self.guard.has_active_threat = True

        # Attempt tap_hold in confirmation zone
        self.device.tap_hold(0.62, 0.667, duration=0.15)
        self.assertEqual(len(self.device.tap_history), 0, "tap_hold in confirmation zone should be vetoed")

        # Attempt tap_hold with veto label
        self.device.tap_hold(0.1, 0.1, duration=0.1, label="Đồng Ý")
        self.assertEqual(len(self.device.tap_history), 0, "tap_hold with veto label should be vetoed")

    def test_mock_device_normal_taps_when_threat_cleared(self):
        self.guard.has_active_threat = True
        self.device.tap(0.62, 0.667)
        self.assertEqual(len(self.device.tap_history), 0)

        # Clear threat
        self.guard.clear_threat()
        self.assertFalse(self.guard.has_active_threat)

        # Normal tap should now go through
        self.device.tap(0.62, 0.667)
        self.assertEqual(len(self.device.tap_history), 1, "Tap should execute after threat is cleared")


class TestInstantReflexLatencyRealOCR(unittest.TestCase):
    """Verifies that ResourceGuard detects resource prompts and executes cancel reflex in < 0.5s with real OCR."""

    def setUp(self):
        self.device = MockDeviceManager()
        self.ocr = OCRService()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard

    def test_execute_instant_cancel_targets_correct_coordinates(self):
        self.guard.execute_instant_cancel()

        self.assertEqual(len(self.device.tap_history), 1)
        event = self.device.tap_history[0]
        # Point(0.376, 0.667)
        self.assertAlmostEqual(event["x"], 0.376, delta=0.04)
        self.assertAlmostEqual(event["y"], 0.667, delta=0.04)

    def test_execute_instant_cancel_latency_under_50ms(self):
        t0 = time.perf_counter()
        result = self.guard.execute_instant_cancel()
        elapsed = time.perf_counter() - t0

        self.assertTrue(result)
        self.assertLess(elapsed, 0.05, f"Instant cancel dispatch took {elapsed*1000:.1f}ms, expected < 50ms")

    def test_scan_and_protect_end_to_end_reflex_latency_under_500ms(self):
        frame = create_synthetic_frame_with_text(
            "Bổ sung Sức Mạnh Khai Phá bằng Ngọc Ánh Sao",
            width=2752,
            height=2064,
            pos=(900, 950),
            font_size=42,
        )

        t0 = time.perf_counter()
        event = self.guard.scan_and_protect(frame)
        elapsed = time.perf_counter() - t0

        self.assertIsNotNone(event, "Resource threat should be detected")
        self.assertEqual(event.threat_type, ThreatType.RESOURCE_THREAT)
        self.assertEqual(event.keyword, "Ngọc Ánh Sao")
        self.assertTrue(event.dismissed, "Event should be marked dismissed after reflex cancel")
        self.assertLess(
            elapsed,
            0.50,
            f"End-to-end reflex latency was {elapsed*1000:.1f}ms, must be < 500ms (0.5s)",
        )
        self.assertEqual(len(self.device.tap_history), 1, "Reflex cancel tap must be dispatched to device")

    def test_scan_and_protect_clean_frame_yields_none(self):
        clean_frame = create_synthetic_frame_with_text(
            "Huấn Luyện Thường Ngày 500/500",
            width=1200,
            height=800,
            pos=(300, 350),
            font_size=36,
        )

        event = self.guard.scan_and_protect(clean_frame)
        self.assertIsNone(event)
        self.assertEqual(len(self.device.tap_history), 0)


class TestCallbacksAndLifecycle(unittest.TestCase):
    """Verifies callbacks dispatch, threat history, and lifecycle reset."""

    def setUp(self):
        self.device = MockDeviceManager()
        self.ocr = OCRService()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)

    def test_callback_invoked_on_threat(self):
        dispatched_events: List[ThreatEvent] = []
        self.guard.register_callback(lambda e: dispatched_events.append(e))

        frame = create_synthetic_frame_with_text(
            "Chi phí: 160 Stellar Jade",
            width=1200,
            height=800,
            pos=(300, 350),
            font_size=36,
        )

        event = self.guard.scan_and_protect(frame)
        self.assertIsNotNone(event)
        self.assertEqual(len(dispatched_events), 1)
        self.assertEqual(dispatched_events[0], event)

    def test_reset_lifecycle(self):
        self.guard.has_active_threat = True
        self.guard.security_violations.append({"violation": "test"})
        self.guard.threat_history.append(
            ThreatEvent(ThreatType.RESOURCE_THREAT, "Warp", time.time())
        )

        self.guard.reset()
        self.assertFalse(self.guard.has_active_threat)
        self.assertIsNone(self.guard.active_threat)
        self.assertEqual(len(self.guard.security_violations), 0)
        self.assertEqual(len(self.guard.threat_history), 0)


if __name__ == "__main__":
    unittest.main()
