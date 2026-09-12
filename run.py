#!/usr/bin/env python3
"""Main entrypoint for BotControl - Honkai: Star Rail on iPad Pro M5."""
import sys
import argparse
import logging
import uvicorn
from bot.web.server import app, run_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BotControl")


def main():
    parser = argparse.ArgumentParser(description="BotControl - Honkai: Star Rail Automation on iPad Pro M5")
    parser.add_argument("--host", default="0.0.0.0", help="Web dashboard host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port (default: 8000)")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode without web server")
    parser.add_argument("--task", choices=["daily", "resin", "dialogue"], help="Task to run in CLI mode")
    parser.add_argument("--runs", type=int, default=6, help="Resin runs count (default: 6)")

    args = parser.parse_args()

    if args.cli:
        from bot.core.device import DeviceManager
        from bot.cv.ocr_service import OCRService
        from bot.cv.matcher import TemplateMatcher
        from bot.tasks.daily import DailyTask
        from bot.tasks.resin import ResinFarmTask
        from bot.tasks.dialogue import DialogueFastSkipTask

        logger.info("Chế độ CLI khởi động...")
        device = DeviceManager()
        if not device.connect():
            logger.warning("Chưa thể kết nối WDA. Vui lòng đảm bảo WDA đang chạy trên iPad tại localhost:8100.")

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
        else:
            logger.error("Vui lòng chỉ định --task [daily|resin|dialogue] khi dùng --cli")
            sys.exit(1)
    else:
        logger.info(f"Khởi động Web Dashboard tại: http://localhost:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
