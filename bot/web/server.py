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

from bot.core.coordinates import HSRZones, Point, BoundingBox
from bot.core.device import DeviceManager, VideoFrame
from bot.cv.ocr_service import OCRService
from bot.cv.matcher import TemplateMatcher
from bot.tasks.base import BaseTask
from bot.tasks.daily import DailyTask
from bot.tasks.resin import ResinFarmTask
from bot.tasks.dialogue import DialogueFastSkipTask
from bot.tasks.simulated_universe import SimulatedUniverseTask
from bot.tasks.smart_pipeline import SmartPipelineTask
from bot.tasks.story import StoryQuestTask
from bot.cv.vlm_solver import OmniRouteVLMSolver

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

# Cached telemetry
cached_power: Optional[dict] = None
cached_fuel: Optional[int] = None


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
        if len(log_history) > 300:
            log_history.pop(0)

    coros = [ws.send_text(json.dumps(entry)) for ws in list(websocket_clients)]
    if coros:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for c in coros:
                    asyncio.create_task(c)
        except Exception:
            pass


class TaskStartRequest(BaseModel):
    task: str  # "daily", "resin", "dialogue", "simulated_universe"
    config: Optional[dict] = None


class TouchRequest(BaseModel):
    x: float
    y: float
    normalized: bool = True


class QuickActionRequest(BaseModel):
    action: str  # "open_phone", "open_guidebook", "close_modal", "open_map", "auto_battle"


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
        "trailblaze_power": cached_power,
        "fuel_count": cached_fuel,
        "antiban_active": getattr(device, "enable_human_touch", True),
        "active_stream_clients": get_active_stream_clients(),
    }


@app.post("/api/antiban/toggle")
async def toggle_antiban():
    device.enable_human_touch = not getattr(device, "enable_human_touch", True)
    broadcast_log(f"🛡️ Anti-Ban Human Touch đã được {'BẬT' if device.enable_human_touch else 'TẮT'}.", "warning" if not device.enable_human_touch else "info")
    return {"antiban_active": device.enable_human_touch}


def generate_placeholder_frame(text: str = "iPad Đang Ngắt Kết Nối WDA") -> bytes:
    """Generates a placeholder image when iPad screen is unavailable."""
    img = np.zeros((720, 960, 3), dtype=np.uint8)
    img[:] = (20, 22, 32)
    cv2.putText(
        img,
        "BotControl - iPad Pro 13 (M5)",
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
        (50, 350),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (180, 180, 190),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        img,
        "Chay: ./scripts/run_wda.sh tren Terminal",
        (50, 410),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (120, 120, 130),
        1,
        cv2.LINE_AA,
    )
    ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ret else b""


def start_background_workers():
    """Starts frame producer and telemetry monitor in the background."""
    device.start_frame_producer()
    t = threading.Thread(target=telemetry_worker_loop, daemon=True, name="TelemetryWorker")
    t.start()


def telemetry_worker_loop():
    """Out-of-band telemetry monitor: samples Trailblaze Power & Fuel without lagging the video stream."""
    global cached_power, cached_fuel
    while True:
        try:
            if device.connected and device.last_screenshot is not None:
                ocr = get_ocr()
                p = ocr.extract_trailblaze_power(device.last_screenshot)
                if p:
                    cached_power = {"current": p[0], "max": p[1]}
                f = ocr.extract_fuel_count(device.last_screenshot)
                if f is not None:
                    cached_fuel = f
        except Exception:
            pass
        time.sleep(8.0)


active_stream_clients = 0
active_stream_clients_lock = threading.Lock()


def get_active_stream_clients() -> int:
    with active_stream_clients_lock:
        return active_stream_clients


def mjpeg_frame_generator(max_frames: Optional[int] = None):
    """High-speed generator streaming pre-rendered JPEG frames from RAM at 18-25 FPS (~22 FPS).
    
    Decoupled from WDA USB traffic: all clients read the pre-encoded frame buffer in RAM.
    Handles client disconnects cleanly without resource or socket leaks.
    """
    global active_stream_clients
    with active_stream_clients_lock:
        active_stream_clients += 1
    logger.debug(f"Stream client connected. Total active clients: {active_stream_clients}")

    frames_sent = 0
    try:
        while True:
            if max_frames is not None and frames_sent >= max_frames:
                break

            try:
                frame_bytes = None
                if device.connected:
                    vf = device.get_video_frame()
                    if vf is not None and vf.jpeg_bytes:
                        frame_bytes = vf.jpeg_bytes
                    else:
                        frame_bytes = device.get_screenshot_jpeg_bytes()

                if frame_bytes:
                    header = (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame_bytes)}\r\n\r\n".encode("ascii")
                    )
                    yield header + frame_bytes + b"\r\n"
                    frames_sent += 1
                    time.sleep(0.016)  # ~60 FPS buttery smooth cadence
                    continue

                # Placeholder when not connected or no frame available
                placeholder = generate_placeholder_frame(
                    "Chờ kết nối WDA qua cổng USB: localhost:8100"
                )
                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(placeholder)}\r\n\r\n".encode("ascii")
                )
                yield header + placeholder + b"\r\n"
                frames_sent += 1
                time.sleep(0.2)

            except (GeneratorExit, asyncio.CancelledError, BrokenPipeError, ConnectionResetError):
                logger.debug("Stream client connection closed by client.")
                break
            except Exception as e:
                logger.debug(f"Stream generation tick exception: {e}")
                time.sleep(0.05)

    except (GeneratorExit, asyncio.CancelledError):
        logger.debug("Stream generator exited cleanly.")
    finally:
        with active_stream_clients_lock:
            active_stream_clients = max(0, active_stream_clients - 1)
        logger.debug(f"Stream client disconnected. Total active clients: {active_stream_clients}")


@app.websocket("/ws/stream")
async def websocket_screen_stream(websocket: WebSocket):
    """High-speed 60 FPS binary JPEG screen stream via WebSocket with zero DOM overhead."""
    await websocket.accept()
    global active_stream_clients
    with active_stream_clients_lock:
        active_stream_clients += 1
    logger.info("WebSocket 60 FPS screen client connected.")
    try:
        while True:
            frame_bytes = None
            if device.connected:
                vf = device.get_video_frame()
                if vf is not None and vf.jpeg_bytes:
                    frame_bytes = vf.jpeg_bytes
                else:
                    frame_bytes = device.get_screenshot_jpeg_bytes()
            if frame_bytes:
                await websocket.send_bytes(frame_bytes)
            await asyncio.sleep(0.016)  # 60 FPS cadence
    except (WebSocketDisconnect, ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        with active_stream_clients_lock:
            active_stream_clients = max(0, active_stream_clients - 1)
        logger.info("WebSocket 60 FPS screen client disconnected.")


@app.get("/api/stream")
async def video_feed():
    """MJPEG screen stream endpoint serving pre-encoded frames from RAM at up to 60 FPS."""
    return StreamingResponse(
        mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, pre-check=0, post-check=0, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        },
    )


@app.post("/api/touch")
async def handle_touch(req: TouchRequest):
    """Sends touch tap from Web Dashboard to iPad."""
    device.tap(req.x, req.y, normalized=req.normalized)
    return {"status": "ok", "x": req.x, "y": req.y}


@app.post("/api/quick_action")
async def handle_quick_action(req: QuickActionRequest):
    """Executes predefined standard game shortcut buttons."""
    act = req.action
    if act == "open_phone":
        device.tap(HSRZones.PHONE_MENU_ICON.x, HSRZones.PHONE_MENU_ICON.y, normalized=True)
    elif act == "open_guidebook":
        device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
    elif act == "close_modal":
        device.tap(HSRZones.GUIDEBOOK_CLOSE.x, HSRZones.GUIDEBOOK_CLOSE.y, normalized=True)
    elif act == "open_map":
        device.tap(HSRZones.MAP_ICON.x, HSRZones.MAP_ICON.y, normalized=True)
    elif act == "auto_battle":
        device.tap_box(HSRZones.BATTLE_AUTO_TOGGLE, normalized=True)
    elif act == "speed_2x":
        device.tap_box(HSRZones.BATTLE_SPEED_TOGGLE, normalized=True)
    else:
        return JSONResponse({"status": "error", "message": f"Hành động không rõ: {act}"}, status_code=400)

    broadcast_log(f"Phím tắt nhanh: {act}", "info")
    return {"status": "ok", "action": act}


@app.get("/api/inspect")
async def inspect_screen():
    """Inspects screen and returns OCR results and energy metrics."""
    global cached_power, cached_fuel
    img = device.get_screenshot()
    if img is None:
        # Try reading the sample image if not connected to device
        sample_path = "/Users/hoangson/.gemini/antigravity/brain/713e9e95-1cd0-4b93-8f33-b38b09fac9bb/.user_uploaded/media_1789194683106.png"
        if os.path.exists(sample_path):
            img = cv2.imread(sample_path)

    if img is None:
        return {"status": "error", "message": "Không có ảnh màn hình"}

    ocr = get_ocr()
    results = ocr.recognize(img)
    power = ocr.extract_trailblaze_power(img)
    fuel = ocr.extract_fuel_count(img)

    if power:
        cached_power = {"current": power[0], "max": power[1]}
    if fuel is not None:
        cached_fuel = fuel

    h, w = img.shape[:2]
    items = []
    for r in results:
        items.append({
            "text": r.text,
            "score": round(r.score, 2),
            "box": r.box.to_int_coords(),
            "center": [round(r.center.x / w, 3), round(r.center.y / h, 3)],
        })

    return {
        "status": "ok",
        "power": cached_power,
        "fuel": cached_fuel,
        "items_count": len(items),
        "items": items,
    }


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
                "mode": cfg.get("mode", "character_target"),
                "category": cfg.get("category", "calyx_golden"),
                "sub_target": cfg.get("sub_target", ""),
                "character_item": cfg.get("character_item", "relic"),
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
    elif req.task == "simulated_universe":
        current_task = SimulatedUniverseTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "mode": cfg.get("mode", "divergent"),
                "preferred_path": cfg.get("preferred_path", "Ký Ức"),
                "target_runs": int(cfg.get("runs", 1)),
            },
            daemon=True,
        )
    elif req.task == "smart_pipeline":
        current_task = SmartPipelineTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "target_type": cfg.get("target_type", "relic"),
                "runs": int(cfg.get("runs", 6)),
                "skip_resin": bool(cfg.get("skip_resin", False)),
            },
            daemon=True,
        )
    elif req.task == "story":
        current_task = StoryQuestTask(device, ocr, matcher, log_callback=broadcast_log)
        task_thread = threading.Thread(
            target=current_task.run,
            kwargs={
                "max_duration_s": float(cfg.get("max_duration_s", 600.0)),
                "solve_puzzles": bool(cfg.get("solve_puzzles", True)),
                "auto_sprint": bool(cfg.get("auto_sprint", True)),
            },
            daemon=True,
        )
    else:
        return JSONResponse({"status": "error", "message": f"Tác vụ không hợp lệ: {req.task}"}, status_code=400)

    task_thread.start()
    broadcast_log(f"Đã khởi động tác vụ: {req.task}", "info")
    return {"status": "started", "task": req.task}


@app.post("/api/story/solve_puzzle")
async def solve_puzzle_api():
    """Triggers on-demand VLM puzzle solving using Gemini 3.8 Flash via OmniRoute."""
    frame = device.get_screenshot()
    if frame is None:
        return JSONResponse({"status": "error", "message": "Không có ảnh màn hình thiết bị"}, status_code=400)

    vlm = OmniRouteVLMSolver()
    broadcast_log("Đang phân tích và giải câu đố bằng Gemini 3.8 Flash qua OmniRoute...", "info")
    plan = vlm.solve_puzzle(frame)
    reasoning = plan.get("reasoning", "")
    broadcast_log(f"🧠 AI Giải Đố: {reasoning}", "info")

    actions = plan.get("actions", [])
    executed = 0
    if actions:
        executed = vlm.execute_plan(plan, device)
        broadcast_log(f"✅ Đã thực thi {executed} bước giải đố thành công!", "info")

    return {
        "status": "ok",
        "puzzle_type": plan.get("puzzle_type", "unknown"),
        "reasoning": reasoning,
        "actions_count": len(actions),
        "executed_count": executed,
    }



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
        with lock:
            history_copy = list(log_history)
        for item in history_copy:
            await websocket.send_text(json.dumps(item))

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in websocket_clients:
            websocket_clients.remove(websocket)


@app.on_event("startup")
async def on_startup():
    start_background_workers()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
