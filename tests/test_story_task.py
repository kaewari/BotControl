"""Unit tests for StoryQuestTask: Navigation, Dialogue, Anti-Stuck & Zero-Spend Guard."""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.core.human_touch import ThreatEvent, ThreatType
from bot.core.resource_guard import ResourceGuard, SecurityViolationError
from bot.tasks.story import StoryQuestTask
from tests.mock_wda import MockDevice, MockOCRService, MockTemplateMatcher


class TestStoryQuestTask(unittest.TestCase):

    def setUp(self):
        self.device = MockDevice()
        self.ocr = MockOCRService()
        self.matcher = MockTemplateMatcher()
        self.guard = ResourceGuard(device=self.device, ocr=self.ocr)
        self.task = StoryQuestTask(
            device=self.device,
            ocr=self.ocr,
            matcher=self.matcher,
            resource_guard=self.guard,
        )

    def test_init_state(self):
        self.assertEqual(self.task.state, "SEEK_AND_MOVE")
        self.assertFalse(self.task.is_running)
        self.assertEqual(self.task.metrics["move_steps"], 0)

    def test_is_dialogue_active_skip_text(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        self.ocr.find_any_text = MagicMock(return_value=("Bỏ qua", MagicMock(text="Bỏ qua")))
        self.assertTrue(self.task._is_dialogue_active(frame))

    def test_is_puzzle_screen_detected(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        self.ocr.find_any_text = MagicMock(return_value=("Đồng Hồ Mộng Mị", MagicMock(text="Đồng Hồ Mộng Mị")))
        self.assertTrue(self.task._is_puzzle_screen(frame))

    def test_handle_dialogue_safe_choice(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        # Mock 2 dialogue choices: 1 risky with "Ngọc Ánh Sao", 1 safe with "Tiếp tục đi"
        item_risky = MagicMock(text="Mua thêm bằng Ngọc Ánh Sao", center=Point(200, 100))
        item_safe = MagicMock(text="Tôi đồng ý, hãy bắt đầu nào", center=Point(200, 200))
        self.ocr.recognize = MagicMock(return_value=[item_risky, item_safe])

        self.task._handle_dialogue(frame)
        self.assertGreater(len(self.device.taps), 0)
        # Verify that the tapped option was the safe one
        last_tap_label = self.device.taps[-1].get("label", "")
        self.assertNotIn("Ngọc Ánh Sao", last_tap_label)
        self.assertIn("Tôi đồng ý", last_tap_label)

    def test_handle_navigation_normal_step(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        # Mock quest marker detected at center
        self.task.marker_detector.detect_quest_marker = MagicMock(return_value=(Point(0.50, 0.45), 0.9))
        self.task.servoing.update_stuck_state = MagicMock(return_value=False)

        initial_moves = self.task.metrics["move_steps"]
        self.task._handle_navigation(frame, step_counter=1, auto_sprint=False)
        self.assertEqual(self.task.metrics["move_steps"], initial_moves + 1)
        self.assertGreater(len(self.device.swipes), 0)

    def test_handle_navigation_anti_stuck_trigger(self):
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        # Simulate stuck detected
        self.task.servoing.update_stuck_state = MagicMock(return_value=True)

        self.task._handle_navigation(frame, step_counter=1, auto_sprint=False)
        self.assertEqual(self.task.metrics["stuck_recoveries"], 1)
        # Should execute back-step swipe and camera pan
        self.assertGreaterEqual(len(self.device.swipes), 2)

    def test_threat_blocking_in_loop(self):
        # Frame with threat keyword
        frame = np.zeros((800, 1000, 3), dtype=np.uint8)
        self.task.capture = MagicMock(return_value=frame)
        # Mock guard detects threat
        import time
        mock_threat = ThreatEvent(threat_type=ThreatType.RESOURCE_THREAT, keyword="Ngọc Ánh Sao", timestamp=time.time(), bbox=BoundingBox(0.4, 0.4, 0.6, 0.6))
        self.guard.scan_and_protect = MagicMock(return_value=mock_threat)

        # Run task briefly
        with patch.object(self.task, "sleep_cancellable", side_effect=lambda s: setattr(self.task, "stop_requested", True)):
            self.task.run(max_duration_s=1.0)

        self.assertGreaterEqual(self.task.metrics["threats_blocked"], 1)


if __name__ == "__main__":
    unittest.main()
