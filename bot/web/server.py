"""FastAPI Web Dashboard Server with Live Screen Stream, WebSocket Logs, and Task Controls."""
import os
import time
import json
import asyncio
import logging
import threading
from typing import Dict, List, Optional
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot.core.device import DeviceManager
from bot.cv.ocr_service import OCRService
from bot.cv.matcher import TemplateMatcher
from bot.tasks.base import BaseTask
from bot.tasks.daily import DailyTask
from bot.tasks.resin import ResinFarmTask
from bot.tasks.dialogue import DialogueFastSkipTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BotControl.Web")

app = FastAPI(title="BotControl - Honkai: Star Rail")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

# Global instances
device = DeviceManager()
ocr_service: Optional[OCRService] = None
matcher = TemplateMatcher()

current_task: Optional[BaseTask] = None
task_thread: Optional[threading.Thread] = None
log_history: List[dict] = []
websocket_clients: List[WebSocket] = []
lock = threading.Lock()


def get_ocr() -> OCRService:
    global ocr_service
    if ocr_service is None:
        ocr_service = OCRService()
    return ocr_service


def broadcast_log(message: str, level: str = "info"):
    entry = {
        "timestamp": time.strftime("%H:%M:%S"),
        "message": message,
        "level": level,
    }
    with lock:
        log_history.append(entry)
        if len(log_history) > 200:
            log_history.pop(0)

    # Async broadcast to connected websockets
    coros = [ws.send_text(json.dumps(entry)) for ws in list(websocket_clients)]
    if coros:
        # Schedule sending in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for c in coros:
                    asyncio.create_task(c)
        except Exception:
            pass


class TaskStartRequest(BaseModel):
    task: str  # "daily", "resin", "dialogue"
    config: Optional[dict] = None


class TouchRequest(BaseModel):
    x: float
    y: float
    normalized: bool = True


@app.get("/")
async def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>BotControl Backend Running. Dashboard file missing.</h1>")


@app.get("/api/status")
async def get_status():
    connected = device.check_connection()
    is_task_running = current_task.is_running if current_task else False
    task_name = current_task.task_name if current_task else None
    return {
        "device_connected": connected,
        "device_wda_url": device.wda_url,
        "resolution": {"width": device.width, "height": device.height},
        "task_running": is_task_running,
        "task_name": task_name,
        "task_paused": current_task.pause_requested if current_task else False,
    }


def generate_placeholder_frame(text: str = "iPad Đang Ngắt Kết Nối WDA") -> bytes:
    """Generates a placeholder image when iPad screen is unavailable."""
    img = np.zeros((720, 960, 3), dtype=np.uint8)
    img[:] = (26, 26, 36)  # Dark slate background
    # Add title
    cv2.putText(
        img,
        "BotControl - iPad Pro M5",
        (50, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 215, 255),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        text,
        (50, 360),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (180, 180, 190),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        "Kiem tra: Cabled USB-C / chay scripts/run_wda.sh",
        (50, 420),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (120, 120, 130),
        1,
        cv2.LINE_AA,
    )
    ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ret else b""


def mjpeg_frame_generator():
    """Generator streaming JPEG frames for MJPEG video stream."""
    while True:
        try:
            if device.connected:
                frame_bytes = device.get_screenshot_jpeg_bytes()
                if frame_bytes:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )
                    time.sleep(0.08)  # ~12 FPS
                    continue

            # Fallback placeholder
            placeholder = generate_placeholder_frame(
                "Chờ kết nối WDA qua cổng USB: localhost:8100"
            )
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + placeholder + b"\r\n"
            )
            time.sleep(1.0)
        except Exception as e:
            time.sleep(1.0)


@app.get("/api/stream")
async def video_feed():
    """MJPEG screen stream endpoint."""
    return StreamingResponse(
        mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/api/touch")
async def handle_touch(req: TouchRequest):
    """Sends touch tap from Web Dashboard to iPad."""
    device.tap(req.x, req.y, normalized=req.normalized)
    return {"status": "ok", "x": req.x, "y": req.y}


@app.post("/api/task/start")
async def start_task(req: TaskStartRequest):
    global current_task, task_thread

    if current_task and current_task.is_running:
        return JSONResponse({"status": "error", "message": "Một tác vụ khác đang chạy"}, status_code=400)

    ocr = get_ocr()
    cfg = req.config or {}

    if req.task == "daily":
        current_task = DailyTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "claim_assignments": cfg.get("claim_assignments", True),
                "claim_training": cfg.get("claim_training", True),
            },
            daemon=True,
        )
    elif req.task == "resin":
        current_task = ResinFarmTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "category": cfg.get("category", "calyx_golden"),
                "sub_target": cfg.get("sub_target", "exp"),
                "runs": int(cfg.get("runs", 6)),
                "use_fuel": bool(cfg.get("use_fuel", False)),
            },
            daemon=True,
        )
    elif req.task == "dialogue":
        current_task = DialogueFastSkipTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "interval": float(cfg.get("interval", 0.3)),
                "auto_skip": bool(cfg.get("auto_skip", True)),
            },
            daemon=True,
        )
    else:
        return JSONResponse({"status": "error", "message": f"Tác vụ không hợp lệ: {req.task}"}, status_code=400)

    task_thread.start()
    broadcast_log(f"Đã khởi động tác vụ: {req.task}", "info")
    return {"status": "started", "task": req.task}


@app.post("/api/task/stop")
async def stop_task():
    global current_task
    if current_task and current_task.is_running:
        current_task.stop()
        broadcast_log("Đã gửi tín hiệu dừng khẩn cấp.", "warning")
        return {"status": "stopping"}
    return {"status": "idle", "message": "Không có tác vụ nào đang chạy"}


@app.post("/api/task/pause")
async def pause_task():
    global current_task
    if current_task and current_task.is_running:
        current_task.pause()
        return {"status": "paused"}
    return {"status": "idle"}


@app.post("/api/task/resume")
async def resume_task():
    global current_task
    if current_task and current_task.is_running:
        current_task.resume()
        return {"status": "resumed"}
    return {"status": "idle"}


@app.get("/api/logs")
async def get_logs():
    with lock:
        return list(log_history)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.append(websocket)
    try:
        # Send history
        with lock:
            history_copy = list(log_history)
        for item in history_copy:
            await websocket.send_text(json.dumps(item))

        # Keep alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in websocket_clients:
            websocket_clients.remove(websocket)


# Mount static assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
