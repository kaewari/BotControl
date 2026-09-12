"""Resin (Sức Mạnh Khai Phá) spending automation for Calyx, Cavern of Corrosion, Bosses."""
import time
from typing import Optional
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.tasks.base import BaseTask


class ResinFarmTask(BaseTask):
    """Automates farming Calyx, Relics, and weekly bosses to spend Trailblaze Power."""

    def run(
        self,
        category: str = "calyx_golden",
        sub_target: str = "exp",
        runs: int = 6,
        use_fuel: bool = False,
        max_fuel_count: int = 0,
    ):
        self.is_running = True
        self.stop_requested = False
        self.log(f"Bắt đầu Xả Nhựa: Danh mục={category}, Loại={sub_target}, Số đợt={runs}, Dùng bình={use_fuel}")

        try:
            # 1. Điều hướng mở Sổ Tay Hướng Dẫn -> Chỉ Số Sinh Tồn
            if not self.navigate_to_survival_index():
                self.log("Không thể vào Chỉ Số Sinh Tồn", level="error")
                return

            # 2. Chọn loại phó bản theo cấu hình
            if not self.select_dungeon(category, sub_target):
                self.log(f"Không thể chọn phó bản: {category}/{sub_target}", level="error")
                return

            # 3. Chuẩn bị khiêu chiến: Điều chỉnh số đợt (1-6) và nhấn Bắt đầu
            if not self.prepare_and_start_battle(runs):
                self.log("Không thể bắt đầu khiêu chiến", level="error")
                return

            # 4. Vòng lặp giám sát trận đấu (Auto Battle + Lặp lại)
            completed_batches = 0
            while not self.stop_requested:
                self.log("Đang trong trận chiến, theo dõi tiến độ...")
                # Đảm bảo bật Auto Battle và 2x Speed
                self.ensure_combat_settings()

                # Chờ kết thúc trận
                battle_ended = self.wait_for_battle_end(timeout_seconds=300)
                if not battle_ended:
                    self.log("Quá thời gian chờ trận đấu kết thúc (Timeout)", level="warning")
                    break

                completed_batches += 1
                self.log(f"Hoàn thành đợt chiến đấu thứ {completed_batches}!")

                # Kiểm tra có tiếp tục Thách Đấu Lại không
                if not self.stop_requested:
                    repeat_result = self.handle_battle_result()
                    if repeat_result == "repeat":
                        self.log("Tiếp tục thách đấu lại đợt tiếp theo...")
                        self.sleep_cancellable(2.0)
                        continue
                    else:
                        self.log("Đã thoát khỏi phó bản sau khi hoàn thành.")
                        break

            self.log(f"✅ Hoàn tất chu trình xả nhựa! Tổng số đợt đã chạy: {completed_batches}")

        except Exception as e:
            self.log(f"Lỗi trong quá trình xả nhựa: {e}", level="error")
        finally:
            self.is_running = False

    def navigate_to_survival_index(self) -> bool:
        """Opens Guidebook and selects Survival Index tab."""
        self.log("Mở Sổ tay Hướng dẫn...")
        self.device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
        self.sleep_cancellable(2.0)

        img = self.capture()
        if img is None:
            return False

        # Chọn tab 'Chỉ Số Sinh Tồn' (Survival Index)
        tab = self.ocr.find_any_text(
            img,
            ["Chỉ Số Sinh Tồn", "Chi So Sinh Ton", "Survival Index"]
        )
        if tab:
            _, res = tab
            self.log(f"Chọn tab '{res.text}'...")
            self.device.tap(res.center.x, res.center.y, normalized=False)
            self.sleep_cancellable(1.5)
            return True

        self.log("Không tìm thấy tab 'Chỉ Số Sinh Tồn', thử tìm lại...", level="warning")
        return False

    def select_dungeon(self, category: str, sub_target: str) -> bool:
        """Selects the requested dungeon category on the left and target on the right."""
        img = self.capture()
        if img is None:
            return False

        h, w = img.shape[:2]
        left_col = BoundingBox(0, 0, w * 0.35, h)

        # 1. Chọn danh mục bên trái
        cat_keywords = {
            "calyx_golden": ["Đài Hoa Nhân Tạo (Vàng)", "Dai Hoa Nhan Tao (Vang)", "Đài Hoa Vàng", "Golden"],
            "calyx_crimson": ["Đài Hoa Nhân Tạo (Đỏ)", "Dai Hoa Nhan Tao (Do)", "Đài Hoa Đỏ", "Crimson"],
            "cavern_corrosion": ["Vết Tích Xâm Thực", "Vet Tich Xam Thuc", "Cavern of Corrosion"],
            "stagnant_shadow": ["Bóng Hình Ngưng Trệ", "Bong Hinh Ngung Tre", "Stagnant Shadow"],
            "echo_of_war": ["Dư Âm Chiến Đấu", "Du Am Chien Dau", "Echo of War"],
        }

        keywords = cat_keywords.get(category, cat_keywords["calyx_golden"])
        match = self.ocr.find_any_text(img, keywords, region=left_col)
        if match:
            _, m_res = match
            self.log(f"Chọn danh mục: '{m_res.text}'")
            self.device.tap(m_res.center.x, m_res.center.y, normalized=False)
            self.sleep_cancellable(1.5)
        else:
            self.log(f"Không thấy danh mục {category} trong cột trái, dùng mặc định vị trí đầu tiên.")
            self.device.tap(0.20, 0.25, normalized=True)
            self.sleep_cancellable(1.5)

        # 2. Bấm nút Dịch chuyển / Khiêu chiến ở góc dưới bên phải
        img_btn = self.capture()
        if img_btn is not None:
            teleport_btn = self.ocr.find_any_text(
                img_btn,
                ["Dịch Chuyển", "Dich Chuyen", "Khiêu Chiến", "Khieu Chien", "Teleport"]
            )
            if teleport_btn:
                _, tp_res = teleport_btn
                self.log(f"Bấm '{tp_res.text}' để di chuyển đến phó bản...")
                self.device.tap(tp_res.center.x, tp_res.center.y, normalized=False)
                self.sleep_cancellable(3.0)
                return True

        return False

    def prepare_and_start_battle(self, runs: int) -> bool:
        """Adjusts wave slider/buttons and clicks Start Challenge."""
        self.log(f"Chuẩn bị vào trận, số đợt: {runs}...")
        self.sleep_cancellable(2.0)

        img = self.capture()
        if img is None:
            return False

        # Tăng số đợt khiêu chiến nếu > 1 bằng nút '+'
        if runs > 1:
            plus_btn = self.ocr.find_any_text(img, ["+", "＋"])
            if plus_btn:
                _, p_res = plus_btn
                # Nhấn dấu cộng nhiều lần tương ứng với runs
                for _ in range(min(runs - 1, 5)):
                    self.device.tap(p_res.center.x, p_res.center.y, normalized=False)
                    self.sleep_cancellable(0.3)

        # Tìm và nhấn nút 'Bắt đầu khiêu chiến'
        start_img = self.capture() or img
        start_btn = self.ocr.find_any_text(
            start_img,
            ["Bắt Đầu Khiêu Chiến", "Bat Dau Khieu Chien", "Khiêu Chiến", "Start Challenge", "Bắt Đầu"]
        )
        if start_btn:
            _, s_res = start_btn
            self.log(f"Bấm '{s_res.text}'...")
            self.device.tap(s_res.center.x, s_res.center.y, normalized=False)
            self.sleep_cancellable(2.5)

            # Kiểm tra xem có popup 'Bổ sung Sức Mạnh Khai Phá' (hết nhựa) không
            fuel_popup = self.check_out_of_resin()
            if fuel_popup:
                self.log("Đã hết Sức Mạnh Khai Phá!", level="warning")
                # Đóng popup
                self.device.tap(0.04, 0.05, normalized=True)
                return False

            return True

        self.log("Không tìm thấy nút 'Bắt đầu khiêu chiến'", level="error")
        return False

    def check_out_of_resin(self) -> bool:
        """Checks if out of resin popup appears."""
        img = self.capture()
        if img is None:
            return False
        popup = self.ocr.find_any_text(
            img,
            ["Bổ sung", "Bo sung", "Bình Năng Lượng", "Ngọc Ánh Sao", "Khôi phục"]
        )
        return popup is not None

    def ensure_combat_settings(self):
        """Verifies and turns on Auto-Battle and 2x Speed during combat."""
        self.sleep_cancellable(3.0)
        img = self.capture()
        if img is None:
            return

        # Vùng góc trên bên phải hiển thị icon Auto Battle & 2x Speed
        self.log("Đảm bảo bật Auto Battle và Tốc độ x2...")
        # Bấm vào khu vực nút Auto Battle nếu chưa bật
        self.device.tap_box(HSRZones.BATTLE_AUTO_TOGGLE, normalized=True)
        self.sleep_cancellable(0.4)
        # Bấm khu vực nút 2x Speed
        self.device.tap_box(HSRZones.BATTLE_SPEED_TOGGLE, normalized=True)
        self.sleep_cancellable(0.4)

    def wait_for_battle_end(self, timeout_seconds: float = 300.0) -> bool:
        """Monitors screen until victory/defeat screen appears."""
        start_time = time.time()
        self.log("Đang theo dõi trận chiến...")

        while time.time() - start_time < timeout_seconds:
            if self.stop_requested:
                return False

            img = self.capture()
            if img is not None:
                # Kiểm tra các chữ kết thúc trận
                end_match = self.ocr.find_any_text(
                    img,
                    ["Thách Đấu Lại", "Thach Dau Lai", "Chiến Thắng", "Chien Thang", "Rút Lui", "Rut Lui", "Thoát"]
                )
                if end_match:
                    _, res = end_match
                    self.log(f"Trận đấu kết thúc: Nhận diện '{res.text}'")
                    return True

            self.sleep_cancellable(2.5)

        return False

    def handle_battle_result(self) -> str:
        """Handles battle end screen: repeats challenge or exits."""
        img = self.capture()
        if img is None:
            return "exit"

        # Tìm nút 'Thách Đấu Lại'
        repeat_btn = self.ocr.find_any_text(
            img,
            ["Thách Đấu Lại", "Thach Dau Lai", "Khiêu Chiến Lại", "Repeat"]
        )
        if repeat_btn:
            _, r_res = repeat_btn
            self.log(f"Bấm '{r_res.text}' để tiếp tục đợt mới...")
            self.device.tap(r_res.center.x, r_res.center.y, normalized=False)
            self.sleep_cancellable(2.0)

            # Kiểm tra xem có bị hết nhựa sau trận không
            if self.check_out_of_resin():
                self.log("Hết nhựa khi bấm Thách đấu lại. Rút lui...", level="warning")
                self.device.tap(0.04, 0.05, normalized=True)
                self.sleep_cancellable(1.0)
                return "exit"

            return "repeat"

        # Thoát nếu không tìm thấy Thách đấu lại
        exit_btn = self.ocr.find_any_text(
            img,
            ["Rút Lui", "Rut Lui", "Thoát", "Xác nhận", "Exit"]
        )
        if exit_btn:
            _, e_res = exit_btn
            self.log(f"Bấm '{e_res.text}' để thoát trận...")
            self.device.tap(e_res.center.x, e_res.center.y, normalized=False)
            self.sleep_cancellable(2.0)

        return "exit"
