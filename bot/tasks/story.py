"""Story Quest & Event Automation Task with 3D Navigation, Smart Dialogue, and AI Puzzle Solving."""
import math
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
import cv2
import numpy as np

from bot.core.coordinates import Point, BoundingBox, HSRZones
from bot.core.resource_guard import ResourceGuard, SecurityViolationError
from bot.cv.navigation import MinimapTracker, QuestMarkerDetector, VisualServoingController
from bot.cv.vlm_solver import OmniRouteVLMSolver
from bot.tasks.base import BaseTask
from bot.tasks.dialogue import DialogueFastSkipTask

logger = logging.getLogger("BotControl.StoryTask")


class StoryQuestTask(BaseTask):
    """Automates story quests, 3D overworld exploration, dialogue progression, and event puzzles."""

    def __init__(
        self,
        device: Any,
        ocr: Optional[Any] = None,
        matcher: Optional[Any] = None,
        log_callback: Optional[Any] = None,
        resource_guard: Optional[ResourceGuard] = None,
        vlm_solver: Optional[OmniRouteVLMSolver] = None,
    ):
        super().__init__(device=device, ocr=ocr, matcher=matcher, log_callback=log_callback)
        self.guard = resource_guard or ResourceGuard(device=self.device, ocr=self.ocr)
        if hasattr(self.device, "resource_guard"):
            self.device.resource_guard = self.guard

        self.minimap = MinimapTracker()
        self.marker_detector = QuestMarkerDetector()
        self.servoing = VisualServoingController()
        self.vlm = vlm_solver or OmniRouteVLMSolver()
        self.dialogue_subtask = DialogueFastSkipTask(self.device, self.ocr, self.matcher, log_callback=self.log_callback)

        self.current_quest_title = "Chưa phát hiện"
        self.state = "SEEK_AND_MOVE"  # "SEEK_AND_MOVE", "INTERACT", "DIALOGUE", "PUZZLE"
        self.metrics: Dict[str, Any] = {
            "move_steps": 0,
            "dialogue_turns": 0,
            "puzzles_solved": 0,
            "threats_blocked": 0,
            "stuck_recoveries": 0,
            "success": False,
        }

    def run(
        self,
        max_duration_s: float = 300.0,
        solve_puzzles: bool = True,
        auto_sprint: bool = True,
    ) -> Dict[str, Any]:
        """Executes the story quest state machine loop."""
        self.is_running = True
        self.stop_requested = False
        start_time = time.perf_counter()

        self.log("🚀 [StoryQuestTask] Khởi động AI tự động chạy cốt truyện & sự kiện...")
        self.log("🛡️ [Zero-Spend Guard] Kích hoạt bảo vệ tuyệt đối Ngọc Ánh Sao & Vé Roll.")

        if hasattr(self.device, "check_connection") and not self.device.check_connection():
            self.log("LỖI: WDA chưa kết nối tới iPad!", level="error")
            self.is_running = False
            return self.metrics

        step_counter = 0

        try:
            while not self.stop_requested and (time.perf_counter() - start_time < max_duration_s):
                frame = self.capture()
                if frame is None:
                    self.sleep_cancellable(0.2)
                    continue

                # 0. Check Zero-Spend Threat
                threat = self.guard.scan_and_protect(frame)
                if threat:
                    self.log(f"🛡️ [RESOURCE GUARD] Phát hiện và vô hiệu hóa popup nguy cơ: {threat.keyword}", level="warning")
                    self.metrics["threats_blocked"] += 1
                    self.sleep_cancellable(0.5)
                    continue

                # 1. State: DIALOGUE Check (Has high priority)
                if self._is_dialogue_active(frame):
                    self.state = "DIALOGUE"
                    self._handle_dialogue(frame)
                    continue

                # 2. State: PUZZLE Check (Dream ticker / event puzzle screen)
                if solve_puzzles and self._is_puzzle_screen(frame):
                    self.state = "PUZZLE"
                    self._handle_puzzle(frame)
                    continue

                # 3. State: INTERACTION PROMPT Check (Approaching NPC or object)
                prompt_res = self.marker_detector.detect_interaction_prompt(frame, self.ocr)
                if prompt_res is not None:
                    pt, prompt_text = prompt_res
                    self.log(f"💬 Phát hiện tương tác: '{prompt_text}'. Đang kích hoạt...", level="info")
                    self.device.tap(pt.x, pt.y, normalized=True, label=prompt_text)
                    self.sleep_cancellable(0.6)
                    continue

                # 4. State: 3D NAVIGATION (Seek Quest Marker & Move)
                self.state = "SEEK_AND_MOVE"
                step_counter += 1
                self._handle_navigation(frame, step_counter, auto_sprint)

            self.metrics["success"] = not self.stop_requested
            self.log(
                f"✅ [StoryQuestTask] Hoàn tất phiên chạy cốt truyện! "
                f"Di chuyển: {self.metrics['move_steps']} bước, "
                f"Hội thoại: {self.metrics['dialogue_turns']} lượt, "
                f"Giải đố: {self.metrics['puzzles_solved']} câu đố, "
                f"Chặn nguy cơ: {self.metrics['threats_blocked']} lần."
            )

        except SecurityViolationError as sve:
            self.log(f"🚨 [RESOURCE GUARD INTERCEPT] Ngăn chặn hành vi vi phạm: {sve}", level="error")
            self.metrics["threats_blocked"] += 1
        except Exception as e:
            logger.exception("Lỗi trong quá trình chạy StoryQuestTask")
            self.log(f"Lỗi trong quá trình chạy StoryQuestTask: {e}", level="error")
        finally:
            self.is_running = False

        return self.metrics

    def _is_dialogue_active(self, frame: np.ndarray) -> bool:
        """Determines if the game is currently inside a dialogue sequence."""
        # Top-right skip button or absence of main HUD virtual joystick
        skip_box = HSRZones.DIALOGUE_SKIP_BUTTON
        h, w = frame.shape[:2]
        crop = frame[int(skip_box.y1 * h):int(skip_box.y2 * h), int(skip_box.x1 * w):int(skip_box.x2 * w)]
        if crop.size > 0:
            res = self.ocr.find_any_text(crop, ["Bỏ qua", "Bo qua", "Skip"])
            if res:
                return True

        # Check for dialogue selection choices in the middle-right area
        mid_right = frame[int(h * 0.35):int(h * 0.75), int(w * 0.55):int(w * 0.95)]
        if mid_right.size > 0:
            text_items = self.ocr.recognize(mid_right)
            if len(text_items) >= 2:
                # Often multiple choice options
                return True

        return False

    def _handle_dialogue(self, frame: np.ndarray):
        """Advances dialogue safely, clicking skip or selecting safe progression options."""
        self.log("🗣️ Đang trong phân cảnh đối thoại cốt truyện...")
        self.metrics["dialogue_turns"] += 1

        # Check for dialogue choices
        h, w = frame.shape[:2]
        choices_roi = frame[int(h * 0.35):int(h * 0.75), int(w * 0.50):int(w * 0.95)]
        items = self.ocr.recognize(choices_roi) if choices_roi.size > 0 else []

        if items:
            # Pick first safe option that doesn't violate ResourceGuard
            selected = None
            for item in items:
                norm_x = (int(w * 0.50) + item.center.x) / float(w)
                norm_y = (int(h * 0.35) + item.center.y) / float(h)
                if self.guard.detect_resource_threat(item.text):
                    continue
                if self.guard.has_active_threat and self.guard.is_vetoed_tap(norm_x, norm_y, label=item.text):
                    continue
                selected = (norm_x, norm_y, item.text)
                break

            if selected:
                sx, sy, stext = selected
                self.log(f"Chọn nhánh đối thoại: '{stext[:30]}...'")
                self.device.tap(sx, sy, normalized=True, label=stext)
                self.sleep_cancellable(0.4)
                return

        # Safe tap on dialogue text area to advance text
        self.device.tap(HSRZones.DIALOGUE_SAFE_TAP.x, HSRZones.DIALOGUE_SAFE_TAP.y, normalized=True)
        self.sleep_cancellable(0.25)

    def _is_puzzle_screen(self, frame: np.ndarray) -> bool:
        """Determines whether the screen contains an event mini-game or puzzle."""
        h, w = frame.shape[:2]
        top_banner = frame[0:int(h * 0.20), 0:w]
        if top_banner.size == 0:
            return False

        puzzle_keywords = [
            "Đồng Hồ Mộng Mị", "Dong Ho Mong Mi", "Dream Ticker",
            "Ghép Tranh", "Ghep Tranh", "Laser", "Gương Phản Chiếu",
            "Hanu", "Origami", "Vượt Ống Cống", "Mở Khóa"
        ]
        match = self.ocr.find_any_text(top_banner, puzzle_keywords)
        return match is not None

    def _handle_puzzle(self, frame: np.ndarray):
        """Invokes Gemini 3.8 Flash via OmniRoute to solve the puzzle."""
        self.log("🧩 Phát hiện câu đố / mini-game! Đang gửi hình ảnh lên Gemini 3.8 Flash qua OmniRoute...", level="info")
        plan = self.vlm.solve_puzzle(frame, context_hint=f"Active Quest: {self.current_quest_title}")
        reasoning = plan.get("reasoning", "")
        self.log(f"🧠 [AI Suy Luận]: {reasoning}")

        actions = plan.get("actions", [])
        if actions:
            executed = self.vlm.execute_plan(plan, self.device, sleep_func=lambda s: self.sleep_cancellable(s))
            self.log(f"✅ Đã thực thi {executed} bước hành động từ AI.")
            self.metrics["puzzles_solved"] += 1
        else:
            self.log("AI chưa đưa ra được bước giải cụ thể, đợi thao tác bổ sung...", level="warning")
            self.sleep_cancellable(1.0)

    def _handle_navigation(self, frame: np.ndarray, step_counter: int, auto_sprint: bool):
        """Tracks quest marker and drives virtual joystick and camera."""
        # 1. Detect 3D Quest Marker
        marker_res = self.marker_detector.detect_quest_marker(frame)
        marker_pt = marker_res[0] if marker_res else None

        # 2. Check Anti-Stuck condition
        if self.servoing.update_stuck_state(frame):
            self.log("⚠️ Nhân vật bị kẹt vật cản. Đang thực hiện thao tác lùi & né...", level="warning")
            self.metrics["stuck_recoveries"] += 1
            # Back up for 0.5s (+pi/2)
            self.device.joystick_drag(math.pi / 2.0, magnitude=0.8, duration=0.5)
            self.sleep_cancellable(0.1)
            # Pan camera 45 degrees to find alternative path
            self.device.camera_pan(0.20, 0.0, duration=0.3)
            self.servoing.reset_stuck()
            return

        # 3. Compute Steering vectors
        pan_dx, pan_dy, joy_angle, joy_mag = self.servoing.compute_steering(marker_pt)

        # 4. Apply camera correction if needed
        if abs(pan_dx) > 0.02:
            self.device.camera_pan(pan_dx, pan_dy, duration=0.25)
            self.sleep_cancellable(0.08)

        # 5. Apply joystick movement
        drag_duration = 0.50
        self.device.joystick_drag(joy_angle, magnitude=joy_mag, duration=drag_duration)
        self.metrics["move_steps"] += 1

        # 6. Natural rhythm: occasional sprint
        if auto_sprint and (step_counter % 5 == 0):
            # Tap sprint button
            self.device.tap(HSRZones.SPRINT_BUTTON.x, HSRZones.SPRINT_BUTTON.y, normalized=True)
            self.sleep_cancellable(0.05)

        # 7. Cognitive pause: human pauses to look around every 14 steps
        if step_counter % 14 == 0:
            self.cognitive_pause(mean=0.6, std=0.2)

        self.sleep_cancellable(0.1)
