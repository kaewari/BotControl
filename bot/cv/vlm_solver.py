"""VLM Solver Interface integrating Gemini 3.8 Flash via OmniRoute for Honkai: Star Rail puzzles & events."""
import os
import json
import base64
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
import cv2
import numpy as np
import requests

logger = logging.getLogger("BotControl.VLMSolver")

SYSTEM_PUZZLE_PROMPT = """You are an expert autonomous AI player for Honkai: Star Rail.
Analyze this game screenshot which contains an interactive puzzle, event mini-game, or dialogue choice.
Formulate a safe, step-by-step action plan to solve it.

All coordinates MUST be normalized [x, y] in range [0.0, 1.0] where [0.0, 0.0] is top-left and [1.0, 1.0] is bottom-right.
NEVER suggest tapping on gacha warp buttons, jade refill confirmations, or spending real-world money/stellar jades.

Respond ONLY with valid JSON matching this schema:
{
  "puzzle_type": "<clockie_puzzle|dream_ticker|laser_routing|dialogue_quiz|event_grid|interactive_screen>",
  "reasoning": "<concise explanation in Vietnamese or English>",
  "solved": <true|false>,
  "actions": [
    {
      "action": "<tap|swipe|hold|wait>",
      "target": [0.50, 0.50],
      "from": [0.30, 0.50],
      "to": [0.60, 0.50],
      "label": "<short description>",
      "delay": 0.4
    }
  ]
}
"""


class OmniRouteVLMSolver:
    """Sends game screenshots to Gemini 3.8 Flash via OmniRoute to solve puzzles and event mechanics."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128")).rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.api_url = f"{self.base_url}/v1/chat/completions"
        else:
            self.api_url = f"{self.base_url}/chat/completions"

        self.api_key = api_key or os.environ.get("OMNIROUTE_API_KEY", "sk-1998af1652270ca2-46610a-194369f3")
        self.model = model or os.environ.get("OMNIROUTE_MODEL", "agy/gemini-3.8-flash-high")
        self.timeout = timeout
        self.max_retries = max_retries

    def encode_frame(self, frame: np.ndarray, quality: int = 80, max_dim: int = 1280) -> str:
        """Resizes frame if needed and encodes to base64 JPEG string."""
        h, w = frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            raise ValueError("Failed to encode frame to JPEG")
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    def solve_puzzle(
        self,
        frame: np.ndarray,
        context_hint: str = "",
        mock_response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyzes frame with Gemini 3.8 Flash and returns structured action plan."""
        if mock_response is not None:
            return mock_response

        if frame is None:
            return {"puzzle_type": "none", "reasoning": "Frame rỗng", "solved": False, "actions": []}

        b64_image = self.encode_frame(frame)
        prompt_text = f"Solve the puzzle in this Honkai: Star Rail screenshot. Context hint: {context_hint}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PUZZLE_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                    ],
                },
            ],
            "max_tokens": 800,
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        retries = 0
        backoff = 1.0

        while retries <= self.max_retries:
            try:
                logger.info(f"🧠 [VLM SOLVER] Gửi yêu cầu giải đố tới {self.model} qua OmniRoute...")
                resp = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)

                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    # Strip markdown block if returned
                    if content.startswith("```json"):
                        content = content[7:]
                    if content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                    parsed = json.loads(content)
                    logger.info(f"✅ [VLM SOLVER] AI đã giải thành công dạng câu đố: {parsed.get('puzzle_type')}")
                    return parsed

                elif resp.status_code == 429:
                    retries += 1
                    logger.warning(f"⚠️ [VLM 429] Rate limit upstream. Đang chờ {backoff:.1f}s trước khi thử lại (lần {retries}/{self.max_retries})...")
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    logger.error(f"❌ [VLM SOLVER] Lỗi HTTP {resp.status_code}: {resp.text[:200]}")
                    break

            except requests.exceptions.Timeout:
                retries += 1
                logger.warning(f"⚠️ [VLM TIMEOUT] Quá thời gian chờ phản hồi VLM ({self.timeout}s). Thử lại...")
                time.sleep(backoff)
                backoff *= 1.5
            except Exception as e:
                logger.error(f"❌ [VLM SOLVER] Ngoại lệ khi gọi OmniRoute: {e}")
                break

        # Fallback return when failed
        return {
            "puzzle_type": "unknown",
            "reasoning": "Không thể kết nối hoặc phân tích qua VLM OmniRoute lúc này",
            "solved": False,
            "actions": [],
        }

    def execute_plan(self, plan: Dict[str, Any], device: Any, sleep_func: Any = time.sleep) -> int:
        """Executes the action sequence from VLM on the device."""
        actions = plan.get("actions", [])
        executed = 0

        for act in actions:
            action_type = act.get("action", "tap").lower()
            label = act.get("label", "")
            delay = float(act.get("delay", 0.4))

            if action_type == "tap":
                target = act.get("target")
                if target and len(target) == 2:
                    tx, ty = float(target[0]), float(target[1])
                    device.tap(tx, ty, normalized=True, label=label)
                    executed += 1
            elif action_type == "swipe":
                p_from = act.get("from")
                p_to = act.get("to")
                dur = float(act.get("duration", 0.4))
                if p_from and p_to and len(p_from) == 2 and len(p_to) == 2:
                    device.swipe(p_from[0], p_from[1], p_to[0], p_to[1], duration=dur, normalized=True)
                    executed += 1
            elif action_type == "hold":
                target = act.get("target")
                dur = float(act.get("duration", 0.5))
                if target and len(target) == 2:
                    device.tap_hold(target[0], target[1], duration=dur, normalized=True, label=label)
                    executed += 1
            elif action_type == "wait":
                secs = float(act.get("seconds", 1.0))
                sleep_func(secs)

            sleep_func(delay)

        return executed
