#!/usr/bin/env python3
"""Main entrypoint for BotControl - Unified Daemon on iPad Pro 13" (M5).

Orchestrates all hardware bridges (WDA, iproxy 8100, iproxy 9100) and Web Dashboard
into a single self-healing supervisor daemon with graceful shutdown.
"""
import sys
import signal
import argparse
import logging
import uvicorn
import yaml
from pathlib import Path

from bot.core.daemon import UnifiedDaemon, set_global_daemon
from bot.web.server import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BotControl")

daemon_instance = None


def load_config() -> dict:
    config_path = Path(__file__).resolve().parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Lỗi đọc config.yaml: {e}")
    return {}


def signal_handler(sig, frame):
    global daemon_instance
    logger.info("🛑 [BOTCONTROL] Nhận tín hiệu dừng (SIGINT/SIGTERM)...")
    if daemon_instance:
        daemon_instance.stop()
    sys.exit(0)


def main():
    global daemon_instance
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    config = load_config()
    device_cfg = config.get("device", {})
    daemon_cfg = config.get("daemon", {})

    parser = argparse.ArgumentParser(description="BotControl - Unified Daemon for Honkai: Star Rail on iPad Pro M5")
    parser.add_argument("--host", default="0.0.0.0", help="Web dashboard host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port (default: 8000)")
    parser.add_argument("--udid", default=device_cfg.get("udid", "00008142-001C64982E09401C"), help="iPad hardware UDID")
    parser.add_argument("--no-wda", "--mock", action="store_true", dest="mock_mode", help="Chạy không kích hoạt WDA/phần cứng")
    parser.add_argument("--cli", action="store_true", help="Chạy chế độ dòng lệnh (CLI)")
    parser.add_argument("--task", choices=["daily", "resin", "dialogue", "smart_pipeline", "story"], help="Tác vụ chạy trong CLI mode")
    parser.add_argument("--runs", type=int, default=6, help="Số lượt chạy xả nhựa (default: 6)")

    args = parser.parse_args()

    # Initialize and start Unified Daemon
    auto_start = daemon_cfg.get("auto_start_wda", True) and not args.mock_mode
    daemon_instance = UnifiedDaemon(
        udid=args.udid,
        wda_port=daemon_cfg.get("wda_port", 8100),
        mjpeg_port=daemon_cfg.get("mjpeg_port", 9100),
        mock_mode=args.mock_mode or not auto_start,
        auto_restart=daemon_cfg.get("auto_restart_wda", True),
    )
    set_global_daemon(daemon_instance)

    if auto_start:
        daemon_instance.start(wait_ready=False)

    try:
        if args.cli:
            from bot.core.device import DeviceManager
            from bot.cv.ocr_service import OCRService
            from bot.cv.matcher import TemplateMatcher
            from bot.tasks.daily import DailyTask
            from bot.tasks.resin import ResinFarmTask
            from bot.tasks.dialogue import DialogueFastSkipTask
            from bot.tasks.smart_pipeline import SmartPipelineTask
            from bot.tasks.story import StoryQuestTask

            logger.info(f"Chế độ CLI khởi động: task={args.task}...")
            if auto_start:
                daemon_instance.wait_for_wda_ready(timeout=daemon_cfg.get("wda_ready_timeout", 30.0))

            device = DeviceManager()
            if not device.connect():
                logger.warning("Chưa thể kết nối WDA. Vui lòng kiểm tra lại thiết bị iPad.")

            ocr = OCRService()
            matcher = TemplateMatcher()

            if args.task == "daily":
                task = DailyTask(device, ocr, matcher)
                task.run()
            elif args.task == "resin":
                task = ResinFarmTask(device, ocr, matcher)
                task.run(runs=args.runs)
            elif args.task == "dialogue":
                task = DialogueFastSkipTask(device, ocr, matcher)
                task.run()
            elif args.task == "smart_pipeline":
                task = SmartPipelineTask(device, ocr, matcher)
                task.run()
            elif args.task == "story":
                task = StoryQuestTask(device, ocr, matcher)
                task.run()
            else:
                logger.error("Vui lòng chỉ định --task [daily|resin|dialogue|smart_pipeline|story] khi dùng --cli")
                sys.exit(1)
        else:
            logger.info("=========================================================")
            logger.info(f"🌐 KHỞI ĐỘNG WEB DASHBOARD: http://localhost:{args.port}")
            logger.info(f"   Trạng thái Daemon: {'ACTIVE (Auto-WDA)' if auto_start else 'MOCK / STANDBY'}")
            logger.info("=========================================================")
            uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        if daemon_instance:
            daemon_instance.stop()


if __name__ == "__main__":
    main()
