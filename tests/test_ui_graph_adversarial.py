"""Adversarial stress-test suite for UI State Graph & Zero-Spend Safety Invariants.

Empirical Challenger M9.2 Test Suite:
1. Monte-Carlo 2D Gaussian touch dispersion across all 145 standard edges (145,000 samples).
   Asserts ZERO samples enter CONFIRMATION_ZONE = BoundingBox(0.55, 0.60, 0.75, 0.72).
2. Adversarial edge injection targeting CONFIRMATION_ZONE center (0.648, 0.667) with label "Xác Nhận".
   Verifies unconditional pre-tap interception and veto before any device tap dispatch.
3. Boundary & perimeter sensitivity analysis: coordinates inside vs outside CONFIRMATION_ZONE.
"""
import unittest
import math
from typing import List, Tuple

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import (
    generate_gaussian_point,
    CONFIRMATION_ZONE,
    RESOURCE_KEYWORDS,
    VETO_KEYWORDS,
)
from bot.core.resource_guard import ResourceGuard, SecurityViolationError
from bot.core.ui_graph import (
    UIStateGraph,
    STANDARD_EDGES,
    STANDARD_NODES,
    UIEdge,
)
from tests.mock_wda import MockDeviceManager


import os
import tempfile

class TestUIGraphAdversarialSafety(unittest.TestCase):
    """Adversarial challenge tests for Zero-Spend Safety & Coordinate Invariants."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.temp_file.close()
        self.device = MockDeviceManager()
        self.guard = ResourceGuard(device=self.device)
        self.device.resource_guard = self.guard
        self.graph = UIStateGraph(filepath=self.temp_file.name, device=self.device, resource_guard=self.guard)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_monte_carlo_touch_dispersion_all_edges(self):
        """Monte-Carlo Simulation: 1,000 Gaussian samples per edge across all 145 edges (145,000 total).

        Asserts that ZERO points out of 145,000 fall inside CONFIRMATION_ZONE.
        """
        total_samples = 0
        violations: List[Tuple[dict, Point]] = []
        min_distance = float("inf")
        closest_edge = None

        def dist_to_box(pt: Point, box: BoundingBox) -> float:
            dx = max(box.x1 - pt.x, 0.0, pt.x - box.x2)
            dy = max(box.y1 - pt.y, 0.0, pt.y - box.y2)
            return math.hypot(dx, dy)

        self.assertEqual(len(STANDARD_EDGES), 145, f"Expected 145 standard edges, got {len(STANDARD_EDGES)}")

        for edge in STANDARD_EDGES:
            center = Point(edge["x"], edge["y"])
            b = edge.get("box")
            box = BoundingBox(b[0], b[1], b[2], b[3]) if b else None

            for _ in range(1000):
                total_samples += 1
                pt = generate_gaussian_point(center=center, box=box)
                d = dist_to_box(pt, CONFIRMATION_ZONE)
                if d < min_distance:
                    min_distance = d
                    closest_edge = edge

                # Check if point falls within CONFIRMATION_ZONE
                if (
                    CONFIRMATION_ZONE.x1 <= pt.x <= CONFIRMATION_ZONE.x2
                    and CONFIRMATION_ZONE.y1 <= pt.y <= CONFIRMATION_ZONE.y2
                ):
                    violations.append((edge, pt))

        self.assertEqual(total_samples, 145000, f"Expected 145,000 samples, got {total_samples}")
        self.assertEqual(
            len(violations),
            0,
            f"Zero-Spend Violation! {len(violations)} sampled points fell inside CONFIRMATION_ZONE: {violations[:5]}",
        )
        self.assertGreater(
            min_distance,
            0.02,
            f"Safety margin too narrow: closest sampled point was {min_distance:.4f} from CONFIRMATION_ZONE",
        )

    def test_adversarial_injection_vetoed_with_guard(self):
        """Adversarial Injection: synthetic edge targeting (0.648, 0.667) with label 'Xác Nhận'.

        Verifies UIStateGraph.navigate() intercepts and halts route, dispatching 0 taps.
        """
        self.graph.add_node("SafeScreenStart")
        self.graph.add_node("MaliciousSpendModal")

        # Inject adversarial transition directly into CONFIRMATION_ZONE
        self.graph.add_edge(
            from_node="SafeScreenStart",
            to_node="MaliciousSpendModal",
            action_type="tap",
            x=0.648,
            y=0.667,
            box=BoundingBox(0.60, 0.64, 0.70, 0.70),
            label="Xác Nhận",
        )

        self.device.clear_history()
        self.guard.security_violations.clear()

        # Attempt navigation
        success = self.graph.navigate(
            "SafeScreenStart",
            "MaliciousSpendModal",
            device=self.device,
            resource_guard=self.guard,
            dry_run=False,
        )

        # Assert unconditional rejection
        self.assertFalse(success, "UIStateGraph.navigate() must return False for adversarial edge")
        self.assertEqual(len(self.device.tap_history), 0, "Zero taps must be executed on device")
        self.assertGreaterEqual(
            len(self.guard.security_violations),
            1,
            "ResourceGuard must log security violation for intercepted tap",
        )

    def test_adversarial_injection_coordinate_veto_without_label(self):
        """Adversarial Injection: synthetic edge in CONFIRMATION_ZONE with harmless/blank label.

        Verifies coordinate-only veto triggers even if label does NOT match VETO_KEYWORDS.
        """
        self.graph.add_node("SafeScreenStart2")
        self.graph.add_node("SpendModalCoordsOnly")

        self.graph.add_edge(
            from_node="SafeScreenStart2",
            to_node="SpendModalCoordsOnly",
            action_type="tap",
            x=0.648,
            y=0.667,
            box=BoundingBox(0.60, 0.64, 0.70, 0.70),
            label="Xem Tiep",  # Harmless label
        )

        self.device.clear_history()
        success = self.graph.navigate(
            "SafeScreenStart2",
            "SpendModalCoordsOnly",
            device=self.device,
            resource_guard=self.guard,
            dry_run=False,
        )

        self.assertFalse(success, "Coordinate in CONFIRMATION_ZONE must be vetoed regardless of label")
        self.assertEqual(len(self.device.tap_history), 0)

    def test_adversarial_injection_label_veto_outside_zone(self):
        """Adversarial Injection: synthetic edge outside CONFIRMATION_ZONE but with VETO label.

        Verifies label veto triggers even if coordinates are outside CONFIRMATION_ZONE.
        """
        self.graph.add_node("SafeScreenStart3")
        self.graph.add_node("SpendModalLabelOnly")

        self.graph.add_edge(
            from_node="SafeScreenStart3",
            to_node="SpendModalLabelOnly",
            action_type="tap",
            x=0.10,
            y=0.10,  # Far from CONFIRMATION_ZONE
            box=BoundingBox(0.05, 0.05, 0.15, 0.15),
            label="Xác Nhận Mua Ngọc Ánh Sao",
        )

        self.device.clear_history()
        success = self.graph.navigate(
            "SafeScreenStart3",
            "SpendModalLabelOnly",
            device=self.device,
            resource_guard=self.guard,
            dry_run=False,
        )

        self.assertFalse(success, "Label matching VETO_KEYWORDS must be vetoed regardless of coordinates")
        self.assertEqual(len(self.device.tap_history), 0)

    def test_adversarial_injection_swipe_into_confirmation_zone(self):
        """Adversarial Injection: swipe gesture ending inside CONFIRMATION_ZONE.

        Verifies swipe actions with end points in CONFIRMATION_ZONE are vetoed.
        """
        self.graph.add_node("SafeScreenStart4")
        self.graph.add_node("SpendModalSwipe")

        self.graph.add_edge(
            from_node="SafeScreenStart4",
            to_node="SpendModalSwipe",
            action_type="swipe",
            x=0.20,
            y=0.20,
            swipe_end_x=0.648,
            swipe_end_y=0.667,
            label="Kéo Đến Xác Nhận",
        )

        self.device.clear_history()
        success = self.graph.navigate(
            "SafeScreenStart4",
            "SpendModalSwipe",
            device=self.device,
            resource_guard=self.guard,
            dry_run=False,
        )

        self.assertFalse(success, "Swipe ending in CONFIRMATION_ZONE must be vetoed")
        self.assertEqual(len(self.device.swipe_history), 0)

    def test_adversarial_injection_fail_closed_without_guard(self):
        """Verify fail-closed Zero-Spend safety: navigate() called with unwired ResourceGuard.

        Confirms UIStateGraph.navigate() fails closed (halts, returns False, dispatches 0 taps)
        even when resource_guard is omitted or None.
        """
        device_unprotected = MockDeviceManager()
        device_unprotected.resource_guard = None  # Unwired guard
        graph_unprotected = UIStateGraph(filepath=self.temp_file.name, device=device_unprotected, resource_guard=None)

        graph_unprotected.add_node("SafeScreenStart5")
        graph_unprotected.add_node("SpendModalUnprotected")
        graph_unprotected.add_edge(
            from_node="SafeScreenStart5",
            to_node="SpendModalUnprotected",
            action_type="tap",
            x=0.648,
            y=0.667,
            box=BoundingBox(0.60, 0.64, 0.70, 0.70),
            label="Xác Nhận",
        )

        device_unprotected.clear_history()
        # Navigate without guard
        success = graph_unprotected.navigate(
            "SafeScreenStart5",
            "SpendModalUnprotected",
            device=device_unprotected,
            resource_guard=None,
            dry_run=False,
        )

        # FAIL-CLOSED ZERO-SPEND SAFETY VERIFICATION:
        self.assertFalse(success, "Fail-closed safety: navigate() must return False even when guard is omitted")
        self.assertEqual(len(device_unprotected.tap_history), 0, "Fail-closed safety: 0 taps dispatched")


if __name__ == "__main__":
    unittest.main()

