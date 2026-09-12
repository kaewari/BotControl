"""Unit tests for OmniRoute VLM Solver integrating Gemini 3.8 Flash."""
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from bot.cv.vlm_solver import OmniRouteVLMSolver
from tests.mock_wda import MockDevice


class TestVLMSolver(unittest.TestCase):

    def setUp(self):
        self.solver = OmniRouteVLMSolver(
            base_url="http://localhost:20128/v1",
            api_key="sk-test-key",
            model="agy/gemini-3.8-flash-high",
            timeout=5.0,
            max_retries=2,
        )
        self.device = MockDevice()

    def test_encode_frame_valid(self):
        frame = np.zeros((300, 400, 3), dtype=np.uint8)
        b64 = self.solver.encode_frame(frame)
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 20)

    def test_solve_puzzle_mock(self):
        mock_plan = {
            "puzzle_type": "clockie_puzzle",
            "reasoning": "Rotate top gear twice to connect road",
            "solved": True,
            "actions": [
                {"action": "tap", "target": [0.55, 0.45], "label": "gear_1", "delay": 0.1},
                {"action": "tap", "target": [0.55, 0.45], "label": "gear_1", "delay": 0.1},
            ],
        }
        res = self.solver.solve_puzzle(np.zeros((100, 100, 3), dtype=np.uint8), mock_response=mock_plan)
        self.assertEqual(res["puzzle_type"], "clockie_puzzle")
        self.assertTrue(res["solved"])
        self.assertEqual(len(res["actions"]), 2)

    def test_execute_plan_mock_device(self):
        plan = {
            "actions": [
                {"action": "tap", "target": [0.5, 0.5], "label": "btn1", "delay": 0.0},
                {"action": "swipe", "from": [0.2, 0.2], "to": [0.8, 0.8], "duration": 0.2, "delay": 0.0},
                {"action": "wait", "seconds": 0.01},
            ]
        }
        executed = self.solver.execute_plan(plan, self.device, sleep_func=lambda s: None)
        self.assertEqual(executed, 2)
        self.assertEqual(len(self.device.taps), 1)
        self.assertEqual(len(self.device.swipes), 1)

    @patch("requests.post")
    def test_solve_puzzle_http_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"puzzle_type": "laser", "reasoning": "aim laser", "solved": true, "actions": []}\n```'
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        res = self.solver.solve_puzzle(frame)
        self.assertEqual(res["puzzle_type"], "laser")
        self.assertTrue(res["solved"])

    @patch("requests.post")
    def test_solve_puzzle_http_429_retry(self, mock_post):
        # 1st call: 429, 2nd call: 200
        resp_429 = MagicMock()
        resp_429.status_code = 429

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"puzzle_type": "retry_ok", "reasoning": "recovered", "solved": true, "actions": []}'
                    }
                }
            ]
        }

        mock_post.side_effect = [resp_429, resp_200]

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        res = self.solver.solve_puzzle(frame)
        self.assertEqual(res["puzzle_type"], "retry_ok")
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
