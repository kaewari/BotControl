"""Unit tests for UnifiedDaemon supervisor and FastAPI daemon endpoints."""
import time
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from bot.core.daemon import UnifiedDaemon, set_global_daemon, get_global_daemon
from bot.web.server import app


class TestUnifiedDaemon(unittest.TestCase):

    def setUp(self):
        self.daemon = UnifiedDaemon(
            udid="00008142-001C64982E09401C",
            wda_port=8100,
            mjpeg_port=9100,
            mock_mode=True,
            auto_restart=False,
            watchdog_interval=0.1,
        )
        set_global_daemon(self.daemon)
        self.client = TestClient(app)

    def tearDown(self):
        if self.daemon:
            self.daemon.stop()

    def test_init_defaults(self):
        self.assertEqual(self.daemon.wda_port, 8100)
        self.assertEqual(self.daemon.mjpeg_port, 9100)
        self.assertEqual(self.daemon.udid, "00008142-001C64982E09401C")
        self.assertTrue(self.daemon.mock_mode)
        self.assertFalse(self.daemon._running)

    def test_mock_start_and_stop(self):
        started = self.daemon.start(wait_ready=False)
        self.assertTrue(started)
        self.assertTrue(self.daemon._running)
        self.assertTrue(self.daemon.is_wda_ready())

        health = self.daemon.health_check()
        self.assertTrue(health["daemon_running"])
        self.assertTrue(health["mock_mode"])
        self.assertEqual(health["udid"], "00008142-001C64982E09401C")
        self.assertTrue(health["wda_ready"])

        self.daemon.stop()
        self.assertFalse(self.daemon._running)

    def test_health_check_keys(self):
        health = self.daemon.health_check()
        required_keys = [
            "daemon_running",
            "mock_mode",
            "udid",
            "wda_port",
            "mjpeg_port",
            "wda_ready",
            "processes",
            "restart_counts",
        ]
        for key in required_keys:
            self.assertIn(key, health)

    @patch("subprocess.run")
    def test_auto_detect_udid_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.stdout = "00008142-TESTUDID123\n"
        mock_run.return_value = mock_proc

        detected = UnifiedDaemon.auto_detect_udid()
        self.assertEqual(detected, "00008142-TESTUDID123")

    @patch("subprocess.run", side_effect=Exception("command not found"))
    def test_auto_detect_udid_fallback(self, mock_run):
        detected = UnifiedDaemon.auto_detect_udid()
        self.assertEqual(detected, "00008142-001C64982E09401C")

    def test_is_port_in_use(self):
        # Port 65534 should not be in use
        self.assertFalse(UnifiedDaemon.is_port_in_use(65534))

    def test_terminate_process_group_mock(self):
        mock_proc = MagicMock()
        mock_proc.pid = 999999
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0

        with patch("os.killpg") as mock_killpg, patch("os.getpgid", return_value=999999):
            self.daemon._terminate_process_group(mock_proc, "mock_task")
            self.assertTrue(mock_killpg.called)

    def test_api_daemon_status(self):
        self.daemon.start(wait_ready=False)
        resp = self.client.get("/api/daemon/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("daemon_running"))
        self.assertTrue(data.get("mock_mode"))

    def test_api_daemon_restart_wda(self):
        self.daemon.start(wait_ready=False)
        resp = self.client.post("/api/daemon/restart_wda")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "restarting")

    def test_api_daemon_safe_mode(self):
        resp = self.client.post("/api/daemon/safe_mode")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "safe_mode_active")


if __name__ == "__main__":
    unittest.main()
