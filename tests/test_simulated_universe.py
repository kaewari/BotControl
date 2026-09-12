"""Unit tests for SimulatedUniverseTask (Divergent Universe & Classic SU)."""
import unittest
from unittest.mock import MagicMock
import numpy as np

from bot.core.coordinates import Point, BoundingBox
from bot.tasks.simulated_universe import SimulatedUniverseTask
from tests.mock_wda import MockDevice, MockOCRService, MockTemplateMatcher


class TestSimulatedUniverseTask(unittest.TestCase):

    def setUp(self):
        self.device = MockDevice()
        self.ocr = MockOCRService()
        self.matcher = MockTemplateMatcher()
        self.task = SimulatedUniverseTask(self.device, self.ocr, self.matcher)

    def test_init_state(self):
        self.assertFalse(self.task.is_running)
        self.assertEqual(self.task.task_name, "SimulatedUniverseTask")

    def test_navigate_to_su_tab_prompt_detected(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.task.capture = MagicMock(return_value=frame)
        self.ocr.find_any_text = MagicMock(return_value=("Vũ Trụ Sai Phân", MagicMock(center=Point(700, 550), text="Vũ Trụ Sai Phân")))

        ok = self.task.navigate_to_su_tab()
        self.assertTrue(ok)
        self.assertGreater(len(self.device.taps), 0)

    def test_start_su_run_divergent(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.task.capture = MagicMock(return_value=frame)
        self.ocr.find_any_text = MagicMock(side_effect=[
            ("Vũ Trụ Sai Phân", MagicMock(center=Point(300, 400), text="Vũ Trụ Sai Phân")),
            ("Bắt đầu tính toán", MagicMock(center=Point(800, 900), text="Bắt đầu tính toán")),
        ])

        ok = self.task.start_su_run(mode="divergent")
        self.assertTrue(ok)
        self.assertGreaterEqual(len(self.device.taps), 2)

    def test_handle_blessing_selection(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.ocr.find_any_text = MagicMock(side_effect=[
            ("Chọn Chúc Phúc", MagicMock(text="Chọn Chúc Phúc")),
            ("Xác nhận", MagicMock(center=Point(850, 900), text="Xác nhận")),
        ])
        self.ocr.find_text = MagicMock(return_value=MagicMock(center=Point(500, 500), text="Chúc Phúc Ký Ức"))

        handled = self.task.handle_blessing_selection(frame, preferred_path="Ký Ức")
        self.assertTrue(handled)
        self.assertGreaterEqual(len(self.device.taps), 2)

    def test_handle_curio_selection(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.ocr.find_any_text = MagicMock(return_value=("Chọn Kỳ Vật", MagicMock(text="Chọn Kỳ Vật")))

        handled = self.task.handle_curio_selection(frame)
        self.assertTrue(handled)
        self.assertGreaterEqual(len(self.device.taps), 2)

    def test_check_in_battle(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        self.ocr.find_any_text = MagicMock(return_value=("Tự động", MagicMock(text="Tự động")))
        self.assertTrue(self.task.check_in_battle(frame))

    def test_move_forward_towards_portal(self):
        self.task.move_forward_towards_portal()
        self.assertGreater(len(self.device.swipes), 0)
        self.assertGreater(len(self.device.taps), 0)


if __name__ == "__main__":
    unittest.main()
