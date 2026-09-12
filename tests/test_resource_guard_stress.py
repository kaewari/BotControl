"""Empirical Stress Test Harness for Zero-Spend ResourceGuard (Challenger M5-1).

Targets:
1. Obfuscated, merged, mixed-case, and noisy OCR texts with sensitive keywords.
2. Boundary value testing on CONFIRMATION_ZONE (corners, edges, just-inside, just-outside, pixel bounds).
3. High-load reflex latency benchmarks over 100 iterations (asserting 100% are < 500ms).
4. Absolute veto leak prevention: zero confirmation taps escape veto when a threat is active.
"""
import os
import time
import threading
import unittest
from typing import List, Dict, Any, Tuple
import numpy as np
import cv2
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
from bot.cv.ocr_service import OCRService, normalize_text, remove_vietnamese_tones
from tests.mock_wda import MockDeviceManager


def create_synthetic_frame(
    text: str,
    width: int = 2752,
    height: int = 2064,
    pos: Tuple[int, int] = (900, 950),
    font_size: int = 42,
    bg_color: Tuple[int, int, int] = (25, 28, 35),
    text_color: Tuple[int, int, int] = (245, 245, 245),
    add_noise: bool = False,
) -> np.ndarray:
    """Generates synthetic game frame with specified text and optional noise."""
    img = Image.new("RGB", (width, height), color=bg_color)
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

    draw.text(pos, text, font=font, fill=text_color)
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    if add_noise:
        noise = np.random.normal(0, 15, bgr.shape).astype(np.int16)
        noisy = np.clip(bgr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        return noisy

    return bgr


class TestAdversarialOCRRobustness(unittest.TestCase):
    """Stress tests keyword detection against obfuscation, merging, and noisy text."""

    def setUp(self):
        self.guard = ResourceGuard()

    def test_merged_text_detection(self):
        """Validates detection when keywords are merged directly into surrounding words without spaces."""
        merged_cases = [
            ("Bổsung60sứcmạnhkhaiphábằngNgọcÁnhSao?", "Ngọc Ánh Sao"),
            ("CanNgocAnhSaodequydoi", "Ngoc Anh Sao"),
            ("160StellarJadeRequiredForReplenish", "Stellar Jade"),
            ("Dùng1VéTinhCầuĐặcBiệtĐểMở", "Vé Tinh Cầu"),
            ("VeTinhCaux10", "Ve Tinh Cau"),
            ("RequiresStarRailPassToWarp", "Star Rail Pass"),
            ("UseStarRailSpecialPassNow", "Star Rail Special Pass"),
            ("ChuyểnĐếnBướcNhảyNhânVật", "Bước Nhảy"),
            ("ExecuteWarpNow", "Warp"),
            ("Quyđổimộngướcbằngngọc", "Quy đổi"),
            ("Nạptổngcộng100000VNĐ", "Nạp"),
        ]
        for phrase, expected_kw in merged_cases:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNotNone(
                detected,
                f"Failed to detect merged keyword in '{phrase}' (expected {expected_kw})",
            )

    def test_case_variation_detection(self):
        """Validates detection across UPPERCASE, lowercase, and mixed-case inputs."""
        case_variations = [
            ("TIÊU HAO NGỌC ÁNH SAO", "Ngọc Ánh Sao"),
            ("ngọc ánh sao", "Ngọc Ánh Sao"),
            ("nGọC ÁnH SaO", "Ngọc Ánh Sao"),
            ("PURCHASE STELLAR JADE", "Stellar Jade"),
            ("stellar jade", "Stellar Jade"),
            ("sTeLlAr JaDe", "Stellar Jade"),
            ("DÙNG VÉ TINH CẦU", "Vé Tinh Cầu"),
            ("vé tinh cầu", "Vé Tinh Cầu"),
            ("vÉ tInH CầU", "Vé Tinh Cầu"),
            ("BƯỚC NHẢY", "Bước Nhảy"),
            ("bước nhảy", "Bước Nhảy"),
            ("bƯớC nHảY", "Bước Nhảy"),
            ("WARP X10", "Warp"),
            ("warp x10", "Warp"),
            ("wArP", "Warp"),
            ("QUY ĐỔI", "Quy đổi"),
            ("quy đổi", "Quy đổi"),
            ("qUy ĐổI", "Quy đổi"),
            ("NẠP TIỀN", "Nạp"),
            ("nạp tiền", "Nạp"),
            ("nẠp", "Nạp"),
        ]
        for phrase, expected_kw in case_variations:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNotNone(
                detected,
                f"Failed to detect case variation in '{phrase}' (expected {expected_kw})",
            )

    def test_whitespace_and_newline_anomalies(self):
        """Validates detection when text has excessive spacing, tabs, or newlines."""
        whitespace_cases = [
            ("Ngọc    Ánh    Sao", "Ngọc Ánh Sao"),
            ("Stellar\tJade", "Stellar Jade"),
            ("Vé\nTinh\nCầu", "Vé Tinh Cầu"),
            ("   Star Rail Pass   \n\t", "Star Rail Pass"),
            ("\n\t Bước \t \n Nhảy \r\n", "Bước Nhảy"),
            ("Quy   \t   đổi", "Quy đổi"),
            ("  Nạp   ", "Nạp"),
        ]
        for phrase, expected_kw in whitespace_cases:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNotNone(
                detected,
                f"Failed to detect keyword with whitespace anomalies in '{repr(phrase)}'",
            )

    def test_surrounding_punctuation_and_symbols(self):
        """Validates detection when keywords are wrapped in brackets, punctuation, or special chars."""
        punctuation_cases = [
            ("[Ngọc Ánh Sao]", "Ngọc Ánh Sao"),
            ("(Stellar Jade: 160)", "Stellar Jade"),
            ("<Vé Tinh Cầu>", "Vé Tinh Cầu"),
            ('"Bước Nhảy"', "Bước Nhảy"),
            ("¿Quy đổi?", "Quy đổi"),
            ("Nạp... 100", "Nạp"),
            ("100% Ngọc Ánh Sao!", "Ngọc Ánh Sao"),
            ("Star Rail Pass / Star Rail Special Pass", "Star Rail Pass"),
        ]
        for phrase, expected_kw in punctuation_cases:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNotNone(
                detected,
                f"Failed to detect keyword wrapped in punctuation in '{phrase}'",
            )

    def test_safe_texts_negative_controls(self):
        """Ensures that normal HSR game UI strings are never falsely flagged as threats."""
        safe_strings = [
            "Huấn Luyện Thường Ngày",
            "Hướng Dẫn Sinh Tồn",
            "Điểm năng động hôm nay: 500/500",
            "Ủy Thác hoàn thành",
            "Bắt đầu khiêu chiến",
            "Tự động chiến đấu x2",
            "Nhận Thưởng",
            "Thẩm Án Xâm Thực",
            "Sức Mạnh Khai Phá: 180/240",
            "Chiến Đấu Tiếp",
            "Rút Lui",
            "Thoát bí cảnh",
            "Cấp Khai Phá: 70",
            "Nhận Tất Cả",
            "Phái Lại Tất Cả",
        ]
        for phrase in safe_strings:
            detected = self.guard.check_text_for_resource_keywords(phrase)
            self.assertIsNone(
                detected,
                f"False positive threat detected on safe string '{phrase}': detected '{detected}'",
            )

    def test_adversarial_noisy_frame_with_real_ocr(self):
        """Tests end-to-end OCR recognition on a synthetic frame with Gaussian noise."""
        ocr = OCRService()
        device = MockDeviceManager()
        guard = ResourceGuard(device=device, ocr=ocr)

        noisy_frame = create_synthetic_frame(
            "Chi phí: 160 Stellar Jade để bổ sung",
            width=2752,
            height=2064,
            pos=(850, 950),
            font_size=42,
            add_noise=True,
        )

        event = guard.scan_and_protect(noisy_frame)
        self.assertIsNotNone(event, "OCR should detect sensitive keyword even on noisy frame")
        self.assertEqual(event.keyword, "Stellar Jade")
        self.assertTrue(event.dismissed)
        self.assertEqual(len(device.tap_history), 1)


class TestConfirmationZoneBoundaryValues(unittest.TestCase):
    """Rigorous boundary value testing of CONFIRMATION_ZONE geometry."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.guard = ResourceGuard(device=self.device)
        # CONFIRMATION_ZONE is BoundingBox(0.55, 0.60, 0.75, 0.72)

    def test_corner_points_exactly_on_boundary(self):
        """All 4 corner points must evaluate to TRUE (inside)."""
        corners = [
            (0.55, 0.60, "Top-Left"),
            (0.75, 0.60, "Top-Right"),
            (0.55, 0.72, "Bottom-Left"),
            (0.75, 0.72, "Bottom-Right"),
        ]
        for x, y, desc in corners:
            self.assertTrue(
                self.guard.is_confirmation_zone(x, y),
                f"Corner {desc} at ({x}, {y}) must be inside CONFIRMATION_ZONE",
            )

    def test_edge_midpoints_exactly_on_boundary(self):
        """Midpoints on all 4 outer edges must evaluate to TRUE (inside)."""
        edge_points = [
            (0.65, 0.60, "Top edge"),
            (0.65, 0.72, "Bottom edge"),
            (0.55, 0.66, "Left edge"),
            (0.75, 0.66, "Right edge"),
        ]
        for x, y, desc in edge_points:
            self.assertTrue(
                self.guard.is_confirmation_zone(x, y),
                f"Edge point {desc} at ({x}, {y}) must be inside CONFIRMATION_ZONE",
            )

    def test_points_just_inside_boundary(self):
        """Points just inside each boundary (delta 0.001) must evaluate to TRUE."""
        inside_points = [
            (0.551, 0.601, "Near Top-Left"),
            (0.749, 0.601, "Near Top-Right"),
            (0.551, 0.719, "Near Bottom-Left"),
            (0.749, 0.719, "Near Bottom-Right"),
            (0.650, 0.660, "Center"),
        ]
        for x, y, desc in inside_points:
            self.assertTrue(
                self.guard.is_confirmation_zone(x, y),
                f"Point {desc} at ({x}, {y}) must be inside CONFIRMATION_ZONE",
            )

    def test_points_just_outside_boundary(self):
        """Points just outside each boundary (delta 0.001) must evaluate to FALSE."""
        outside_points = [
            (0.549, 0.660, "Just Left of Left Edge"),
            (0.751, 0.660, "Just Right of Right Edge"),
            (0.650, 0.599, "Just Above Top Edge"),
            (0.650, 0.721, "Just Below Bottom Edge"),
            (0.549, 0.599, "Top-Left Diagonal Outside"),
            (0.751, 0.599, "Top-Right Diagonal Outside"),
            (0.549, 0.721, "Bottom-Left Diagonal Outside"),
            (0.751, 0.721, "Bottom-Right Diagonal Outside"),
        ]
        for x, y, desc in outside_points:
            self.assertFalse(
                self.guard.is_confirmation_zone(x, y),
                f"Point {desc} at ({x}, {y}) must NOT be inside CONFIRMATION_ZONE",
            )

    def test_pixel_boundary_conversion(self):
        """Verifies exact pixel boundaries against 2752x2064 screen resolution.

        x: 0.55 * 2752 = 1513.6, 0.75 * 2752 = 2064.0
        y: 0.60 * 2064 = 1238.4, 0.72 * 2064 = 1486.08
        """
        # Inside pixels
        px_inside_tl = (1514, 1239)  # norm: (0.55015, 0.60029) -> Inside
        px_inside_br = (2064, 1486)  # norm: (0.75000, 0.71996) -> Inside
        self.assertTrue(self.guard.is_confirmation_zone(*px_inside_tl))
        self.assertTrue(self.guard.is_confirmation_zone(*px_inside_br))

        # Outside pixels
        px_outside_tl = (1513, 1238)  # norm: (0.54978, 0.59981) -> Outside
        px_outside_br = (2065, 1487)  # norm: (0.75036, 0.72045) -> Outside
        self.assertFalse(self.guard.is_confirmation_zone(*px_outside_tl))
        self.assertFalse(self.guard.is_confirmation_zone(*px_outside_br))


class TestHighLoadReflexLatencyBenchmark(unittest.TestCase):
    """Stress test: 100-iteration latency benchmark asserting 100% are < 500ms."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.ocr = OCRService()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.device.resource_guard = self.guard

    def test_100_iterations_reflex_latency_benchmark(self):
        """Executes 100 real end-to-end scan_and_protect passes on 2752x2064 frames.

        Asserts:
        - 100% of iterations < 500ms.
        - Records min, max, mean, median, P95, and P99 latency.
        """
        iterations = 100
        latencies_ms: List[float] = []

        # Create realistic full-resolution frame
        test_frame = create_synthetic_frame(
            "Bổ sung 60 Sức Mạnh Khai Phá bằng 75 Ngọc Ánh Sao?",
            width=2752,
            height=2064,
            pos=(850, 950),
            font_size=42,
        )

        for i in range(iterations):
            self.device.clear_history()
            self.guard.clear_threat()

            t0 = time.perf_counter()
            event = self.guard.scan_and_protect(test_frame)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            latencies_ms.append(elapsed_ms)

            self.assertIsNotNone(event, f"Iteration {i}: Threat must be detected")
            self.assertTrue(event.dismissed, f"Iteration {i}: Threat must be marked dismissed")
            self.assertEqual(len(self.device.tap_history), 1, f"Iteration {i}: Reflex cancel tap dispatched")
            self.assertLess(
                elapsed_ms,
                500.0,
                f"Iteration {i} violated < 500ms constraint: took {elapsed_ms:.1f}ms",
            )

        # Statistical analysis
        arr = np.array(latencies_ms)
        min_lat = float(np.min(arr))
        max_lat = float(np.max(arr))
        mean_lat = float(np.mean(arr))
        median_lat = float(np.median(arr))
        p95_lat = float(np.percentile(arr, 95))
        p99_lat = float(np.percentile(arr, 99))
        pass_count = int(np.sum(arr < 500.0))
        pass_rate = (pass_count / iterations) * 100.0

        print("\n" + "=" * 60)
        print("⚡ [STRESS BENCHMARK] 100-ITERATION REFLEX LATENCY RESULTS")
        print(f"Total Iterations : {iterations}")
        print(f"Iterations < 500ms: {pass_count} / {iterations} ({pass_rate:.1f}%)")
        print(f"Min Latency      : {min_lat:.2f} ms")
        print(f"Mean Latency     : {mean_lat:.2f} ms")
        print(f"Median Latency   : {median_lat:.2f} ms")
        print(f"P95 Latency      : {p95_lat:.2f} ms")
        print(f"P99 Latency      : {p99_lat:.2f} ms")
        print(f"Max Latency      : {max_lat:.2f} ms")
        print("=" * 60 + "\n")

        self.assertEqual(pass_rate, 100.0, "100% of reflex cancel iterations must be < 500ms")

    def test_instant_cancel_dispatch_overhead_100_runs(self):
        """Asserts that execute_instant_cancel() alone has near-zero overhead (< 10ms)."""
        iterations = 100
        overheads_ms: List[float] = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            self.guard.execute_instant_cancel()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            overheads_ms.append(elapsed_ms)

        arr = np.array(overheads_ms)
        self.assertLess(float(np.max(arr)), 10.0, "Instant cancel dispatch must be < 10ms")


class TestAbsoluteVetoLeakPrevention(unittest.TestCase):
    """Empirically verifies that NO confirmation tap ever escapes veto when a threat is active."""

    def setUp(self):
        self.device = MockDeviceManager(width=2752, height=2064)
        self.guard = ResourceGuard(device=self.device)
        self.device.resource_guard = self.guard

    def test_500_random_confirmation_zone_taps_all_blocked(self):
        """Generates 500 random coordinates within CONFIRMATION_ZONE and asserts 100% are blocked."""
        self.guard.has_active_threat = True
        rng = np.random.RandomState(42)

        total_trials = 500
        blocked_count = 0

        for _ in range(total_trials):
            x = rng.uniform(0.55, 0.75)
            y = rng.uniform(0.60, 0.72)
            self.device.tap(x, y)
            # Must not be executed in device
            if len(self.device.tap_history) == 0:
                blocked_count += 1
            else:
                self.fail(f"VETO ESCAPE! Confirmation tap escaped at ({x:.4f}, {y:.4f})")

        self.assertEqual(blocked_count, total_trials, "100% of confirmation zone taps must be blocked")
        self.assertEqual(len(self.guard.security_violations), total_trials)

    def test_all_veto_labels_at_arbitrary_coords_blocked(self):
        """Ensures all veto keywords are blocked even if clicked outside CONFIRMATION_ZONE."""
        self.guard.has_active_threat = True
        test_labels = [
            "Xác Nhận", "xác nhận", "Xac Nhan", "xac nhan",
            "Đồng Ý", "đồng ý", "Dong Y", "dong y",
            "Confirm", "confirm", "Agree", "agree",
        ]

        for label in test_labels:
            self.device.clear_history()
            # Tap far outside confirmation zone, e.g. at (0.1, 0.1)
            self.device.tap(0.10, 0.10, label=label)
            self.assertEqual(
                len(self.device.tap_history),
                0,
                f"VETO ESCAPE! Tap with label '{label}' was not blocked!",
            )

    def test_tap_hold_in_confirmation_zone_all_blocked(self):
        """Ensures tap_hold is equally subject to strict pre-tap veto."""
        self.guard.has_active_threat = True
        for x, y in [(0.56, 0.62), (0.65, 0.66), (0.74, 0.71)]:
            self.device.clear_history()
            self.device.tap_hold(x, y, duration=0.15)
            self.assertEqual(
                len(self.device.tap_history),
                0,
                f"VETO ESCAPE! tap_hold escaped at ({x}, {y})",
            )

    def test_tap_box_in_confirmation_zone_blocked(self):
        """Ensures tap_box targeting confirmation bounding box is blocked."""
        self.guard.has_active_threat = True
        confirm_box = BoundingBox(0.55, 0.60, 0.75, 0.72)
        self.device.tap_box(confirm_box)
        self.assertEqual(len(self.device.tap_history), 0, "tap_box in confirmation zone must be blocked")

    def test_multithreaded_concurrent_veto_stress(self):
        """Stress test: 10 threads concurrently attempting 100 confirmation taps each (1000 total).

        Asserts:
        - Exactly 0 taps reach device tap_history.
        - Exactly 1000 security violations logged.
        - No race conditions or deadlocks.
        """
        self.guard.has_active_threat = True
        num_threads = 10
        taps_per_thread = 100
        threads = []
        escape_count = 0
        lock = threading.Lock()

        def worker(thread_id: int):
            nonlocal escape_count
            rng = np.random.RandomState(thread_id * 100)
            for _ in range(taps_per_thread):
                x = rng.uniform(0.55, 0.75)
                y = rng.uniform(0.60, 0.72)
                self.device.tap(x, y, label="Xác Nhận")
                # Check if device history grew
                with lock:
                    if len(self.device.tap_history) > 0:
                        escape_count += 1

        for tid in range(num_threads):
            t = threading.Thread(target=worker, args=(tid,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(escape_count, 0, "ZERO taps may escape veto under concurrent load")
        self.assertEqual(len(self.device.tap_history), 0, "Tap history must remain empty")
        self.assertEqual(
            len(self.guard.security_violations),
            num_threads * taps_per_thread,
            "Every unauthorized tap must be recorded in security violations log",
        )

    def test_end_to_end_threat_lifecycle_veto_containment(self):
        """Lifecycle verification:

        1. Inactive: Safe tap at confirm coords allowed (during non-threat state).
        2. Threat active: Confirmation tap blocked 100%.
        3. Cancel tap: Allowed.
        4. Threat cleared: Normal operation restored.
        """
        # 1. Inactive threat
        self.guard.has_active_threat = False
        self.device.tap(0.65, 0.66)
        self.assertEqual(len(self.device.tap_history), 1, "Tap allowed when threat is inactive")
        self.device.clear_history()

        # 2. Threat becomes active
        self.guard.has_active_threat = True
        self.device.tap(0.65, 0.66, label="Xác Nhận")
        self.assertEqual(len(self.device.tap_history), 0, "Confirmation tap blocked when threat is active")

        # 3. Cancel button tap is allowed
        self.device.tap(0.376, 0.667, label="Hủy")
        self.assertEqual(len(self.device.tap_history), 1, "Cancel tap must succeed even when threat active")
        self.device.clear_history()

        # 4. Clear threat
        self.guard.clear_threat()
        self.assertFalse(self.guard.has_active_threat)
        self.device.tap(0.65, 0.66)
        self.assertEqual(len(self.device.tap_history), 1, "Tap allowed after threat cleared")


if __name__ == "__main__":
    unittest.main()
