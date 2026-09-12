"""Unit tests for FastAPI endpoints with Mock Device Harness.

Prevents hardware leakage to live iPad Pro (port 8100) during test execution.
"""
import unittest
from starlette.testclient import TestClient
import bot.web.server as server
from bot.web.server import app, generate_placeholder_frame
from tests.mock_wda import MockDeviceManager


class TestWebServer(unittest.TestCase):
    def setUp(self):
        self.mock_device = MockDeviceManager()
        self._orig_device = server.device
        server.device = self.mock_device
        self.client = TestClient(app)

    def tearDown(self):
        server.device = self._orig_device

    def test_get_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_get_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("device_connected", data)
        self.assertIn("task_running", data)
        self.assertIn("trailblaze_power", data)
        self.assertTrue(data["device_connected"])

    def test_quick_action(self):
        response = self.client.post("/api/quick_action", json={"action": "open_guidebook"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")
        # Verify tap intercepted by mock device, not physical hardware
        self.assertTrue(len(self.mock_device.tap_history) > 0)

    def test_inspect_endpoint(self):
        response = self.client.get("/api/inspect")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("items_count", data)

    def test_get_logs(self):
        response = self.client.get("/api/logs")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_placeholder_frame_generation(self):
        frame = generate_placeholder_frame("Test Frame")
        self.assertTrue(len(frame) > 100)
        self.assertTrue(frame.startswith(b"\xff\xd8"))

    def test_touch_endpoint(self):
        """Tests /api/touch endpoint translating web click to iPad tap."""
        response = self.client.post("/api/touch", json={"x": 0.5, "y": 0.5, "normalized": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")
        self.assertTrue(len(self.mock_device.tap_history) > 0)
        last_tap = self.mock_device.tap_history[-1]
        self.assertAlmostEqual(last_tap["x"], 0.5, delta=0.05)

    def test_antiban_toggle_endpoint(self):
        """Tests /api/antiban/toggle endpoint."""
        # Toggle off
        r1 = self.client.post("/api/antiban/toggle")
        self.assertEqual(r1.status_code, 200)
        self.assertIn("antiban_active", r1.json())
        # Toggle on
        r2 = self.client.post("/api/antiban/toggle")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("antiban_active", r2.json())


if __name__ == "__main__":
    unittest.main()
