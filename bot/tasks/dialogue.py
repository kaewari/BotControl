"""Dialogue fast-forwarding and auto-skip task for Honkai: Star Rail."""
import time
from bot.core.coordinates import HSRZones, BoundingBox
from bot.tasks.base import BaseTask


class DialogueFastSkipTask(BaseTask):
    """Continuously taps safe area to fast-forward dialogues and clicks Skip button when available."""

    def run(self, interval: float = 0.3, auto_skip: bool = True):
        self.is_running = True
        self.stop_requested = False
        self.log(f"Bắt đầu Auto-Skip Hội thoại (khoảng cách tap: {interval}s, auto_skip: {auto_skip})")

        cycle_count = 0
        try:
            while not self.stop_requested:
                # 1. Tap the safe dialogue progression area
                self.device.tap(HSRZones.DIALOGUE_SAFE_TAP.x, HSRZones.DIALOGUE_SAFE_TAP.y, normalized=True)
                cycle_count += 1

                # Every 5 cycles (~1.5s), perform OCR check for Skip button or choices
                if auto_skip and cycle_count % 5 == 0:
                    img = self.capture()
                    if img is not None:
                        # Check top-right region for Skip / Bỏ qua
                        h, w = img.shape[:2]
                        top_right_region = BoundingBox(
                            x1=w * 0.75,
                            y1=0,
                            x2=w,
                            y2=h * 0.15,
                        )
                        skip_match = self.ocr.find_any_text(
                            img,
                            ["Bỏ qua", "Bo qua", "Skip"],
                            min_score=0.55,
                            region=top_right_region,
                        )
                        if skip_match is not None:
                            _, match_res = skip_match
                            self.log(f"Phát hiện nút Bỏ qua: '{match_res.text}', đang nhấn...")
                            self.device.tap(match_res.center.x, match_res.center.y, normalized=False)
                            self.sleep_cancellable(0.6)
                            # Often after clicking Skip, a confirmation dialog appears: "Xác nhận"
                            confirm_img = self.capture()
                            if confirm_img is not None:
                                confirm_res = self.ocr.find_any_text(
                                    confirm_img,
                                    ["Xác nhận", "Xac nhan", "Confirm"],
                                    min_score=0.6,
                                )
                                if confirm_res is not None:
                                    _, c_res = confirm_res
                                    self.log(f"Nhấn xác nhận bỏ qua: '{c_res.text}'")
                                    self.device.tap(c_res.center.x, c_res.center.y, normalized=False)

                        # Check if a dialogue choice box is present on the right
                        right_region = BoundingBox(
                            x1=w * 0.55,
                            y1=h * 0.35,
                            x2=w * 0.95,
                            y2=h * 0.75,
                        )
                        # Detect any dialogue prompt bubble
                        dialogue_choice = self.ocr.find_any_text(
                            img,
                            ["...", "?", "!", "Được", "Tôi", "Đi thôi", "Chào"],
                            min_score=0.5,
                            region=right_region,
                        )
                        if dialogue_choice is not None:
                            _, ch_res = dialogue_choice
                            self.log(f"Chọn hội thoại: '{ch_res.text}'")
                            self.device.tap(ch_res.center.x, ch_res.center.y, normalized=False)

                if not self.sleep_cancellable(interval):
                    break

        finally:
            self.is_running = False
            self.log("Đã dừng Auto-Skip Hội thoại.")
