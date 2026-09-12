"""Unified Daemon Supervisor for BotControl on iPad Pro 13" (M5).

Orchestrates all hardware bridges (iproxy 8100, WDA xcodebuild, iproxy 9100),
monitors sub-process health, performs auto-recovery, and guarantees graceful teardown.
"""
import os
import sys
import time
import signal
import socket
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any, Tuple
import requests

logger = logging.getLogger("BotControl.Daemon")


class UnifiedDaemon:
    """Master Supervisor Daemon managing WDA, iproxy bridges, and health watchdog."""

    def __init__(
        self,
        udid: Optional[str] = None,
        wda_port: int = 8100,
        mjpeg_port: int = 9100,
        wda_dir: Optional[str] = None,
        team_id: str = "44T7Y77WAJ",
        mock_mode: bool = False,
        auto_restart: bool = True,
        watchdog_interval: float = 5.0,
    ):
        self.wda_port = wda_port
        self.mjpeg_port = mjpeg_port
        self.team_id = team_id
        self.mock_mode = mock_mode
        self.auto_restart = auto_restart
        self.watchdog_interval = watchdog_interval

        # Paths
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.wda_dir = Path(wda_dir) if wda_dir else base_dir / "WebDriverAgent"

        # Hardware UDID
        self.udid = udid or self.auto_detect_udid()
        self.wda_url = f"http://localhost:{self.wda_port}"

        # Process management
        self.processes: Dict[str, subprocess.Popen] = {}
        self._running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._restart_counts: Dict[str, int] = {"iproxy_wda": 0, "wda_runner": 0, "iproxy_mjpeg": 0}

    @staticmethod
    def auto_detect_udid() -> str:
        """Attempts to discover connected physical iOS device (prioritizing iPad) via idevice_id."""
        try:
            res = subprocess.run(
                ["idevice_id", "-l"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3.0,
            )
            devices = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
            if devices:
                # If multiple devices connected, prioritize iPad
                for d in devices:
                    try:
                        info = subprocess.run(
                            ["ideviceinfo", "-u", d, "-k", "DeviceClass"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=2.0,
                        )
                        if "iPad" in info.stdout:
                            logger.info(f"📱 Tự động phát hiện iPad: {d}")
                            return d
                    except Exception:
                        pass
                logger.info(f"📱 Tự động phát hiện thiết bị iOS: {devices[0]}")
                return devices[0]
        except Exception as e:
            logger.debug(f"Không thể chạy idevice_id: {e}")

        # Fallback default UDID for iPad Pro 13" (M5)
        return "00008142-001C64982E09401C"

    @staticmethod
    def is_port_in_use(port: int) -> bool:
        """Checks if a TCP port is currently open and bound on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    def clean_orphaned_ports(self):
        """Terminates any stale iproxy processes and xcodebuild runners holding ports 8100 or 9100."""
        if self.mock_mode:
            return
        logger.debug("Dọn dẹp các tiến trình iproxy và xcodebuild cũ nếu đang chiếm cổng...")
        try:
            subprocess.run(["pkill", "-f", f"iproxy.*{self.wda_port}"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", f"iproxy.*{self.mjpeg_port}"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "xcodebuild.*WebDriverAgent"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"Lỗi khi dọn dẹp port: {e}")

    def start_iproxy_wda(self) -> bool:
        """Spawns iproxy bridge for WDA command channel (port 8100)."""
        if self.mock_mode:
            return True
        try:
            subprocess.run(["pkill", "-f", f"iproxy.*{self.wda_port}"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.3)
        except Exception:
            pass
        cmd = ["iproxy", f"{self.wda_port}:{self.wda_port}", "-u", self.udid]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            self.processes["iproxy_wda"] = proc
            logger.info(f"🔌 [iproxy {self.wda_port}] Đã khởi chạy (PID: {proc.pid}) kết nối iPad: {self.udid}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khởi chạy iproxy {self.wda_port}: {e}")
            return False

    def start_iproxy_mjpeg(self) -> bool:
        """Spawns iproxy bridge for WDA native MJPEG video stream (port 9100)."""
        if self.mock_mode:
            return True
        try:
            subprocess.run(["pkill", "-f", f"iproxy.*{self.mjpeg_port}"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.3)
        except Exception:
            pass
        cmd = ["iproxy", f"{self.mjpeg_port}:{self.mjpeg_port}", "-u", self.udid]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            self.processes["iproxy_mjpeg"] = proc
            logger.info(f"📹 [iproxy {self.mjpeg_port}] Đã khởi chạy stream bridge (PID: {proc.pid})")
            return True
        except Exception as e:
            logger.error(f"Lỗi khởi chạy iproxy {self.mjpeg_port}: {e}")
            return False

    def start_wda_runner(self) -> bool:
        """Spawns xcodebuild test-without-building for WebDriverAgentRunner."""
        if self.mock_mode:
            return True
        if not self.wda_dir.exists():
            logger.error(f"Không tìm thấy thư mục WebDriverAgent tại: {self.wda_dir}")
            return False

        # Attempt test-without-building first, fallback to test
        cmd = [
            "xcodebuild",
            "test-without-building",
            "-project",
            str(self.wda_dir / "WebDriverAgent.xcodeproj"),
            "-scheme",
            "WebDriverAgentRunner",
            "-destination",
            f"id={self.udid}",
            "-allowProvisioningUpdates",
        ]
        try:
            log_out = open("/tmp/wda_runner.log", "w")
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.wda_dir),
                stdout=log_out,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            self.processes["wda_runner"] = proc
            logger.info(f"🚀 [WDA Runner] Đang khởi chạy WebDriverAgentRunner trên iPad (PID: {proc.pid})...")
            return True
        except Exception as e:
            logger.error(f"Lỗi khởi chạy xcodebuild: {e}")
            return False

    def is_wda_ready(self) -> bool:
        """Checks if WDA HTTP service is accepting requests and ready."""
        if self.mock_mode:
            return True
        try:
            resp = requests.get(f"{self.wda_url}/status", timeout=1.5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("value", {}).get("state", "") == "success" or "sessionId" in data.get("value", {}) or bool(data.get("value"))
        except Exception:
            pass
        return False

    def wait_for_wda_ready(self, timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
        """Polls WDA status until ready or timeout expires."""
        if self.mock_mode:
            return True
        start_time = time.time()
        logger.info(f"⏳ Đang chờ WebDriverAgent sẵn sàng tại {self.wda_url} (timeout: {timeout:.0f}s)...")
        while time.time() - start_time < timeout:
            if self.is_wda_ready():
                logger.info("✅ WebDriverAgent đã sẵn sàng hoạt động!")
                return True
            time.sleep(poll_interval)
        logger.warning(f"⚠️ Quá thời gian chờ WDA ({timeout:.0f}s). Tiếp tục chạy chế độ chờ...")
        return False

    def start(self, wait_ready: bool = True, ready_timeout: float = 30.0) -> bool:
        """Starts all managed subprocesses and watchdog thread."""
        with self._lock:
            if self._running:
                logger.warning("UnifiedDaemon đã đang chạy.")
                return True

            logger.info("=========================================================")
            logger.info("🚀 KHỞI ĐỘNG UNIFIED DAEMON SUPERVISOR - BOTCONTROL")
            logger.info(f"   Thiết bị: iPad Pro 13\" (M5) [{self.udid}]")
            logger.info(f"   WDA Port: {self.wda_port} | MJPEG Port: {self.mjpeg_port}")
            logger.info(f"   Mock Mode: {self.mock_mode}")
            logger.info("=========================================================")

            self.clean_orphaned_ports()

            # 1. Start iproxy 8100
            self.start_iproxy_wda()
            time.sleep(0.5)

            # 2. Start WDA Runner
            self.start_wda_runner()

            # 3. Start iproxy 9100
            self.start_iproxy_mjpeg()

            self._running = True

            # 4. Start watchdog thread
            self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="DaemonWatchdog", daemon=True)
            self._watchdog_thread.start()

        # 5. Wait for WDA to be responsive if requested
        if wait_ready and not self.mock_mode:
            self.wait_for_wda_ready(timeout=ready_timeout)

        return True

    def _terminate_process_group(self, proc: subprocess.Popen, name: str):
        """Gracefully kills a process and its child process group."""
        if proc is None or proc.poll() is not None:
            return

        pid = proc.pid
        logger.info(f"🛑 Dừng tiến trình {name} (PID: {pid})...")

        try:
            if sys.platform != "win32":
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            else:
                proc.terminate()
        except Exception as e:
            logger.debug(f"SIGTERM error on {name}: {e}")

        # Wait up to 2 seconds for graceful exit
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning(f"⚠️ Tiến trình {name} (PID: {pid}) không phản hồi SIGTERM, cưỡng chế SIGKILL...")
            try:
                if sys.platform != "win32":
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception as e:
                logger.debug(f"SIGKILL error on {name}: {e}")

    def stop(self):
        """Stops all subprocesses cleanly and terminates watchdog."""
        with self._lock:
            if not self._running and not self.processes:
                return

            logger.info("🛑 [UNIFIED DAEMON] Đang dừng toàn bộ chuỗi tiến trình con...")
            self._running = False

            for name, proc in list(self.processes.items()):
                self._terminate_process_group(proc, name)

            self.processes.clear()
            self.clean_orphaned_ports()
            logger.info("✅ [UNIFIED DAEMON] Đã dừng toàn diện. Toàn bộ tiến trình và cổng mạng đã giải phóng.")

    def restart_wda(self) -> bool:
        """Restarts WDA runner and iproxy 8100 bridge."""
        logger.info("🔄 [UNIFIED DAEMON] Khởi động lại WDA Runner & iproxy 8100...")
        with self._lock:
            for key in ["wda_runner", "iproxy_wda"]:
                if key in self.processes:
                    self._terminate_process_group(self.processes[key], key)
                    del self.processes[key]

            self.clean_orphaned_ports()
            self.start_iproxy_wda()
            time.sleep(0.5)
            self.start_wda_runner()
            self._restart_counts["wda_runner"] += 1

        return self.wait_for_wda_ready(timeout=30.0)

    def _watchdog_loop(self):
        """Periodically checks sub-processes and auto-recovers if they crash."""
        logger.info("👀 Daemon Watchdog đã kích hoạt.")
        while self._running:
            time.sleep(self.watchdog_interval)
            if not self._running:
                break

            if not self.auto_restart or self.mock_mode:
                continue

            with self._lock:
                # Check iproxy 8100
                p_wda = self.processes.get("iproxy_wda")
                if p_wda and p_wda.poll() is not None:
                    logger.warning(f"⚠️ [WATCHDOG] iproxy 8100 đã thoát (code: {p_wda.poll()}). Đang tự khởi động lại...")
                    self.start_iproxy_wda()
                    self._restart_counts["iproxy_wda"] += 1

                # Check iproxy 9100
                p_mjpeg = self.processes.get("iproxy_mjpeg")
                if p_mjpeg and p_mjpeg.poll() is not None:
                    logger.warning(f"⚠️ [WATCHDOG] iproxy 9100 đã thoát (code: {p_mjpeg.poll()}). Đang tự khởi động lại...")
                    self.start_iproxy_mjpeg()
                    self._restart_counts["iproxy_mjpeg"] += 1

                # Check WDA Runner
                p_run = self.processes.get("wda_runner")
                if p_run and p_run.poll() is not None:
                    logger.warning(f"⚠️ [WATCHDOG] WDA Runner đã thoát (code: {p_run.poll()}). Đang tự khởi động lại...")
                    self.start_wda_runner()
                    self._restart_counts["wda_runner"] += 1

                # Health check: If WDA runner is running but WDA HTTP endpoint is unresponsive, recycle iproxy
                if p_run and p_run.poll() is None and p_wda and p_wda.poll() is None:
                    if not self.is_wda_ready():
                        self._unready_count = getattr(self, "_unready_count", 0) + 1
                        if self._unready_count >= 3:
                            logger.warning("⚠️ [WATCHDOG] WDA không phản hồi qua iproxy 8100. Đang tự khôi phục iproxy bridge...")
                            self.start_iproxy_wda()
                            self._restart_counts["iproxy_wda"] += 1
                            self._unready_count = 0
                    else:
                        self._unready_count = 0

    def health_check(self) -> Dict[str, Any]:
        """Returns comprehensive status dictionary for API and dashboard reporting."""
        status = {
            "daemon_running": self._running,
            "mock_mode": self.mock_mode,
            "udid": self.udid,
            "wda_port": self.wda_port,
            "mjpeg_port": self.mjpeg_port,
            "wda_ready": self.is_wda_ready(),
            "processes": {},
            "restart_counts": dict(self._restart_counts),
        }

        for name, proc in self.processes.items():
            alive = proc.poll() is None
            status["processes"][name] = {
                "pid": proc.pid if alive else None,
                "alive": alive,
                "returncode": proc.poll(),
            }

        return status


# Global daemon instance for easy access
_global_daemon: Optional[UnifiedDaemon] = None


def get_global_daemon() -> Optional[UnifiedDaemon]:
    return _global_daemon


def set_global_daemon(daemon: UnifiedDaemon):
    global _global_daemon
    _global_daemon = daemon
