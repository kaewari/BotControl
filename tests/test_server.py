"""Unit tests for FastAPI endpoints."""
import unittest
from starlette.testclient import TestClient
from bot.web.server import app, generate_placeholder_frame


class TestWebServer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

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

    def test_quick_action(self):
        response = self.client.post("/api/quick_action", json={"action": "open_guidebook"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

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


if __name__ == "__main__":
    unittest.main()
