"""Simulated Universe (Vũ Trụ Mô Phỏng) and Divergent Universe (Vũ Trụ Sai Phân) automation."""
import time
from typing import List, Optional
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.tasks.base import BaseTask


class SimulatedUniverseTask(BaseTask):
    """Automates running Divergent Universe and classic Simulated Universe for weekly points & planar relics."""

    def run(
        self,
        mode: str = "divergent",  # "divergent" (Sai phân) or "classic" (Mô phỏng cổ điển)
        preferred_path: str = "Ký Ức",  # Ký Ức, Hư Vô, Hủy Diệt, Săn Bắn, Tri Thức, Hòa Hợp, Trù Phú, Bảo Hộ
        target_runs: int = 1,
    ):
        self.is_running = True
        self.stop_requested = False
        self.log(f"Bắt đầu Vũ Trụ Mô Phỏng/Sai Phân: Chế độ={mode}, Vận mệnh ưu tiên={preferred_path}, Số lần={target_runs}")

        try:
            # 1. Điều hướng mở Sổ tay -> Tab Vũ Trụ Mô Phỏng
            if not self.navigate_to_su_tab():
                self.log("Không thể mở giao diện Vũ Trụ Mô Phỏng", level="error")
                return

            completed_runs = 0
            while completed_runs < target_runs and not self.stop_requested:
                self.log(f"Khởi động lượt chạy thứ {completed_runs + 1}/{target_runs}...")

                # 2. Bắt đầu khiêu chiến
                if not self.start_su_run(mode):
                    self.log("Không thể bắt đầu lượt chạy", level="error")
                    break

                # 3. Vòng lặp điều hướng phòng và chọn chúc phúc
                run_finished = self.run_exploration_loop(preferred_path)
                if run_finished:
                    completed_runs += 1
                    self.log(f"Hoàn thành lượt chạy {completed_runs}!")
                else:
                    self.log("Lượt chạy kết thúc hoặc bị gián đoạn.")
                    break

            self.log(f"✅ Hoàn tất chu trình Vũ Trụ Mô Phỏng! Đã chạy: {completed_runs} lượt.")

        except Exception as e:
            self.log(f"Lỗi trong quá trình chạy Vũ Trụ: {e}", level="error")
        finally:
            self.is_running = False

    def navigate_to_su_tab(self) -> bool:
        """Opens Guidebook and selects Simulated Universe tab."""
        self.log("Mở Sổ tay Hướng dẫn...")
        self.device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
        self.sleep_cancellable(2.0)

        # Bấm vào Tab 3 (Vũ Trụ Mô Phỏng)
        self.log("Chọn Tab Vũ Trụ Mô Phỏng...")
        self.device.tap(HSRZones.TAB_SIMULATED_UNIVERSE.x, HSRZones.TAB_SIMULATED_UNIVERSE.y, normalized=True)
        self.sleep_cancellable(2.0)
        return True

    def start_su_run(self, mode: str) -> bool:
        """Enters the selected SU mode and launches the domain."""
        img = self.capture()
        if img is None:
            return False

        if mode == "divergent":
            # Tìm Vũ Trụ Sai Phân
            du_btn = self.ocr.find_any_text(
                img,
                ["Vũ Trụ Sai Phân", "Vu Tru Sai Phan", "Sai Phân", "Divergent Universe"]
            )
            if du_btn:
                _, res = du_btn
                self.log(f"Chọn '{res.text}'...")
                self.device.tap(res.center.x, res.center.y, normalized=False)
                self.sleep_cancellable(2.5)

        # Nhấn 'Bắt đầu' / 'Khiêu chiến'
        start_img = self.capture()
        if start_img is not None:
            btn = self.ocr.find_any_text(
                start_img,
                ["Bắt đầu", "Bat dau", "Khiêu chiến", "Khieu chien", "Tiếp tục", "Start", "Vào"]
            )
            if btn:
                _, b_res = btn
                self.log(f"Bấm '{b_res.text}'...")
                self.device.tap(b_res.center.x, b_res.center.y, normalized=False)
                self.sleep_cancellable(3.0)
                return True

        # Fallback bấm góc dưới bên phải
        self.device.tap(0.85, 0.90, normalized=True)
        self.sleep_cancellable(3.0)
        return True

    def run_exploration_loop(self, preferred_path: str, timeout_seconds: float = 1200.0) -> bool:
        """Handles blessings, combat auto-battle, and moving between domains."""
        start_time = time.time()
        self.log("Bắt đầu vòng lặp khám phá các phòng...")

        while time.time() - start_time < timeout_seconds:
            if self.stop_requested:
                return False

            img = self.capture()
            if img is None:
                self.sleep_cancellable(2.0)
                continue

            # 1. Kiểm tra màn hình Chọn Chúc Phúc (Blessing Selection)
            if self.handle_blessing_selection(img, preferred_path):
                self.sleep_cancellable(1.5)
                continue

            # 2. Kiểm tra màn hình Chọn Kỳ Vật (Curio Selection)
            if self.handle_curio_selection(img):
                self.sleep_cancellable(1.5)
                continue

            # 3. Kiểm tra Trận Chiến đang diễn ra
            if self.check_in_battle(img):
                self.log("Đang trong giao tranh, kích hoạt Auto-Battle...")
                self.device.tap_box(HSRZones.BATTLE_AUTO_TOGGLE, normalized=True)
                self.sleep_cancellable(0.3)
                self.device.tap_box(HSRZones.BATTLE_SPEED_TOGGLE, normalized=True)
                self.sleep_cancellable(3.0)
                continue

            # 4. Kiểm tra Kết Thúc Lượt Chạy (Quyết Toán / Hoàn Thành)
            if self.check_run_ended(img):
                self.log("Lượt chạy Vũ Trụ đã hoàn thành / quyết toán điểm!")
                self.sleep_cancellable(2.0)
                # Bấm xác nhận thoát
                self.device.tap(0.50, 0.90, normalized=True)
                self.sleep_cancellable(2.0)
                return True

            # 5. Nếu đang ở ngoài sảnh phòng: Di chuyển thẳng về phía trước để vào cổng
            self.move_forward_towards_portal()
            self.sleep_cancellable(1.5)

        return False

    def handle_blessing_selection(self, img, preferred_path: str) -> bool:
        """Detects blessing screen and chooses best blessing."""
        blessing_screen = self.ocr.find_any_text(
            img,
            ["Chọn Chúc Phúc", "Chon Chuc Phuc", "Chúc Phúc", "Blessing", "Xác nhận chúc phúc"]
        )
        if blessing_screen:
            self.log("Phát hiện màn hình Chọn Chúc Phúc...")
            # Thử tìm chúc phúc theo vận mệnh ưu tiên
            path_match = self.ocr.find_text(img, preferred_path)
            if path_match:
                self.log(f"Ưu tiên chọn Chúc Phúc thuộc '{preferred_path}'")
                self.device.tap(path_match.center.x, path_match.center.y, normalized=False)
            else:
                # Chọn chúc phúc đầu tiên ở giữa màn hình
                self.log("Chọn Chúc Phúc đầu tiên...")
                self.device.tap(0.30, 0.50, normalized=True)

            self.sleep_cancellable(0.8)
            # Bấm 'Xác nhận' ở góc dưới bên phải
            confirm_btn = self.ocr.find_any_text(img, ["Xác nhận", "Xac nhan", "Confirm"])
            if confirm_btn:
                _, c_res = confirm_btn
                self.device.tap(c_res.center.x, c_res.center.y, normalized=False)
            else:
                self.device.tap(0.85, 0.90, normalized=True)
            return True
        return False

    def handle_curio_selection(self, img) -> bool:
        """Detects curio selection and picks first available."""
        curio_screen = self.ocr.find_any_text(img, ["Chọn Kỳ Vật", "Chon Ky Vat", "Kỳ Vật", "Curio"])
        if curio_screen:
            self.log("Chọn Kỳ Vật ngẫu nhiên...")
            self.device.tap(0.35, 0.50, normalized=True)
            self.sleep_cancellable(0.8)
            self.device.tap(0.85, 0.90, normalized=True)
            return True
        return False

    def check_in_battle(self, img) -> bool:
        """Checks if screen is in turn-based combat."""
        return self.ocr.find_any_text(img, ["Tự động", "Tu dong", "Auto", "Nhắc nhở"]) is not None

    def check_run_ended(self, img) -> bool:
        """Checks if end-of-run tally screen is shown."""
        return self.ocr.find_any_text(
            img,
            ["Quyết Toán", "Quyet Toan", "Điểm Tích Lũy", "Hoàn thành khiêu chiến", "Thất Bại"]
        ) is not None

    def move_forward_towards_portal(self):
        """Pushes virtual joystick forward to navigate 3D room."""
        # Kéo cần di chuyển ảo (ở góc dưới bên trái) hướng lên trên
        self.device.swipe(0.18, 0.78, 0.18, 0.55, duration=1.2, normalized=True)
        # Bấm phím tương tác nếu có biểu tượng xuất hiện
        self.device.tap(0.70, 0.70, normalized=True)
