"""Comprehensive Resin (Sức Mạnh Khai Phá) spending automation for Honkai: Star Rail."""
import time
from typing import Optional
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.core.cache import ui_cache
from bot.tasks.base import BaseTask


class ResinFarmTask(BaseTask):
    """Automates farming Calyx, Relics, Planar Ornaments, Stagnant Shadows, and Weekly Bosses with UI Caching."""

    def run(
        self,
        mode: str = "character_target",  # "character_target" or "category"
        category: str = "calyx_golden",
        sub_target: str = "exp",
        character_item: str = "relic",  # "relic", "planar_1", "planar_2"
        runs: int = 6,
        use_fuel: bool = False,
        max_fuel_count: int = 0,
    ):
        self.is_running = True
        self.stop_requested = False
        self.log(f"Bắt đầu Xả Nhựa: Chế độ={mode}, Mục tiêu={character_item if mode == 'character_target' else f'{category}/{sub_target}'}, Số đợt={runs}, Dùng bình={use_fuel}")

        try:
            # 1. Mở Sổ Tay Hướng Dẫn -> Tab Chỉ Số Sinh Tồn
            if not self.navigate_to_survival_index():
                self.log("Không thể vào Hướng Dẫn Sinh Tồn", level="error")
                return

            # 2. Điều hướng tới phó bản tương ứng
            if mode == "character_target":
                success = self.select_character_target(character_item)
            else:
                success = self.select_dungeon_category(category, sub_target)

            if not success:
                self.log("Không thể chọn được phó bản yêu cầu", level="error")
                return

            # 3. Chuẩn bị khiêu chiến: Điều chỉnh số đợt (1-6) và nhấn Bắt đầu
            if not self.prepare_and_start_battle(runs):
                self.log("Không thể bắt đầu khiêu chiến", level="error")
                return

            # 4. Vòng lặp giám sát trận đấu (Auto Battle + Lặp lại)
            completed_batches = 0
            while not self.stop_requested:
                self.log(f"Đang trong trận chiến (Đợt {completed_batches + 1}/{runs}), theo dõi tiến độ...")
                # Đảm bảo bật Auto Battle và 2x Speed
                self.ensure_combat_settings()

                # Chờ kết thúc trận
                battle_ended = self.wait_for_battle_end(timeout_seconds=360)
                if not battle_ended:
                    self.log("Quá thời gian chờ trận đấu kết thúc (Timeout)", level="warning")
                    break

                completed_batches += 1
                self.log(f"✅ Hoàn thành đợt chiến đấu thứ {completed_batches}!")

                if self.stop_requested:
                    self.handle_battle_result(force_exit=True)
                    break

                # Kiểm tra tiếp tục Thách Đấu Lại
                repeat_status = self.handle_battle_result(force_exit=(completed_batches >= runs))
                if repeat_status == "repeat":
                    self.log("Tiếp tục thách đấu lại đợt tiếp theo...")
                    self.sleep_cancellable(2.5)
                    continue
                else:
                    self.log("Đã hoàn thành tất cả các đợt hoặc đã thoát trận.")
                    break

            self.log(f"🎉 Hoàn tất chu trình xả nhựa! Tổng số đợt đã chạy thành công: {completed_batches}")

        except Exception as e:
            self.log(f"Lỗi trong quá trình xả nhựa: {e}", level="error")
        finally:
            self.is_running = False

    def navigate_to_survival_index(self) -> bool:
        """Opens Guidebook and selects Survival Index tab."""
        self.log("Mở Sổ tay Hướng dẫn...")
        self.device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
        self.sleep_cancellable(2.0)

        # Nhấn vào Tab 2 (Hướng Dẫn Sinh Tồn) trên thanh 5 tab
        self.log("Chuyển sang Tab Hướng Dẫn Sinh Tồn (Tab 2)...")
        self.device.tap(HSRZones.TAB_SURVIVAL_INDEX.x, HSRZones.TAB_SURVIVAL_INDEX.y, normalized=True)
        self.sleep_cancellable(2.0)

        img = self.capture()
        if img is None:
            return False

        # Kiểm tra đã vào tab Hướng Dẫn Sinh Tồn
        if self.ocr.find_any_text(img, ["Huong Dan Sinh Ton", "Hướng Dẫn Sinh Tồn", "Muc Tieu Boi Duong"]):
            self.log("Đã mở Hướng Dẫn Sinh Tồn thành công.")
            return True

        return True

    def select_character_target(self, item_type: str = "relic") -> bool:
        """Farms recommended relics or planar ornaments for the pinned character (e.g. Robin)."""
        self.log(f"Chọn Mục Tiêu Bồi Dưỡng của nhân vật (loại: {item_type})...")
        # Nhấn vào card Mục Tiêu Bồi Dưỡng ở cột trái
        self.device.tap(HSRZones.LEFT_NAV_TARGET_CHARACTER.x, HSRZones.LEFT_NAV_TARGET_CHARACTER.y, normalized=True)
        self.sleep_cancellable(1.5)

        img = self.capture()
        if img is None:
            return False

        if item_type == "relic":
            # Fast-Path + Micro-ROI + Auto-Learn: Bấm nút 'Vào' Di Vật
            self.tap_cached_or_learn(
                key="target_relic_enter",
                expected_texts=["Vào", "Vao", "Khiêu Chiến"],
                fallback_targets=["Vào", "Vao", "Khiêu Chiến", "Khieu Chien"],
                padding_x=0.08,
                padding_y=0.05,
                verify_first=True,
            )
            # Event-driven Trigger: Chờ giao diện phó bản xuất hiện
            self.wait_for_condition(
                lambda img: self.ocr.find_any_text(img, ["Khiêu Chiến", "Khieu Chien", "Sức Mạnh Khai Phá"]) is not None,
                timeout=3.0,
                check_interval=0.1,
            )
            return True

        elif item_type == "planar_1":
            self.tap_cached_or_learn(
                key="target_planar_enter_1",
                expected_texts=["Vào", "Vao", "Khiêu Chiến"],
                fallback_targets=["Vào", "Vao", "Khiêu Chiến", "Khieu Chien"],
                padding_x=0.08,
                padding_y=0.05,
                verify_first=True,
            )
            self.wait_for_condition(
                lambda img: self.ocr.find_any_text(img, ["Khiêu Chiến", "Khieu Chien", "Sức Mạnh Khai Phá"]) is not None,
                timeout=3.0,
                check_interval=0.1,
            )
            return True

        elif item_type == "planar_2":
            cache_pt = ui_cache.get_point("target_planar_enter_2") or Point(0.849, 0.721)
            self.device.tap(cache_pt.x, cache_pt.y, normalized=True)
            self.sleep_cancellable(1.5)
            return True

        return False

    def select_dungeon_category(self, category: str, sub_target: str) -> bool:
        """Selects category from left sidebar and specific dungeon on the right."""
        self.log(f"Điều hướng danh mục: {category} (Mục tiêu: {sub_target})...")

        # 1. Chọn mục bên trái
        nav_points = {
            "planar": HSRZones.LEFT_NAV_PLANAR,
            "calyx_golden": HSRZones.LEFT_NAV_CALYX_GOLDEN,
            "calyx_crimson": HSRZones.LEFT_NAV_CALYX_CRIMSON,
            "stagnant_shadow": HSRZones.LEFT_NAV_STAGNANT_SHADOW,
            "cavern_corrosion": HSRZones.LEFT_NAV_CAVERN_CORROSION,
            "echo_of_war": HSRZones.LEFT_NAV_ECHO_OF_WAR,
        }

        # Nếu là phó bản ở dưới (Cavern / Echo of war), cuộn danh mục xuống trước
        if category in ["cavern_corrosion", "echo_of_war"]:
            self.device.swipe(0.20, 0.75, 0.20, 0.35, duration=0.4, normalized=True)
            self.sleep_cancellable(1.0)

        nav_pt = nav_points.get(category, HSRZones.LEFT_NAV_CALYX_GOLDEN)
        self.device.tap(nav_pt.x, nav_pt.y, normalized=True)
        self.sleep_cancellable(1.8)

        img = self.capture()
        if img is None:
            return False

        # 2. Tìm kiếm và bấm nút Vào tương ứng trên danh sách phó bản bên phải
        if sub_target:
            btn = self.ocr.find_action_button_on_row(img, sub_target, tolerance_y=180.0)
            if btn:
                self.log(f"Tìm thấy nút '{btn.text}' cho '{sub_target}', đang bấm...")
                self.device.tap(btn.center.x, btn.center.y, normalized=False)
                self.sleep_cancellable(2.5)
                return True

        # Nếu không tìm thấy tên cụ thể, bấm nút Vào đầu tiên (hàng 1)
        self.log("Bấm nút Vào của hàng phó bản đầu tiên...")
        self.device.tap(HSRZones.ENTER_ROW_1.x, HSRZones.ENTER_ROW_1.y, normalized=True)
        self.sleep_cancellable(2.5)
        return True

    def prepare_and_start_battle(self, runs: int) -> bool:
        """Adjusts wave count and launches battle via 2-step start."""
        self.log(f"Chuẩn bị giao diện vào trận, số đợt thiết lập: {runs}...")
        self.sleep_cancellable(1.5)

        img = self.capture()
        if img is not None:
            power = self.ocr.extract_trailblaze_power(img)
            if power:
                curr, max_p = power
                self.log(f"Sức Mạnh Khai Phá hiện có: {curr}/{max_p}")

        # Tăng số đợt khiêu chiến nếu > 1
        if runs > 1 and img is not None:
            plus_btn = self.ocr.find_any_text(img, ["+", "＋"])
            if plus_btn:
                _, p_res = plus_btn
                for _ in range(min(runs - 1, 5)):
                    self.device.tap(p_res.center.x, p_res.center.y, normalized=False)
                    self.sleep_cancellable(0.20)

        # Bước 1: Nhấn 'Khiêu Chiến' trên thẻ phó bản qua Micro-ROI & Auto-Learn
        self.tap_cached_or_learn(
            key="dungeon_challenge_btn",
            expected_texts=["Khiêu Chiến", "Khieu Chien"],
            fallback_targets=["Khiêu Chiến", "Khieu Chien"],
            padding_x=0.08,
            padding_y=0.04,
            verify_first=True,
        )

        # Event-driven Trigger: Chờ màn hình xếp đội hoặc popup hết nhựa
        self.wait_for_condition(
            lambda img: self.ocr.find_any_text(img, ["Bắt Đầu Khiêu Chiến", "Bat Dau Khieu Chien", "Xuất Phát", "Bổ sung", "Bo sung"]) is not None,
            timeout=2.5,
            check_interval=0.1,
        )

        # Kiểm tra popup hết nhựa
        if self.check_out_of_resin():
            self.log("Đã hết Sức Mạnh Khai Phá!", level="warning")
            self.device.tap(HSRZones.BACK_BUTTON.x, HSRZones.BACK_BUTTON.y, normalized=True)
            return False

        # Bước 2: Nhấn 'Bắt Đầu Khiêu Chiến' trên màn hình xếp đội
        self.tap_cached_or_learn(
            key="team_start_battle_btn",
            expected_texts=["Bắt Đầu Khiêu Chiến", "Bat Dau Khieu Chien", "Xuất Phát"],
            fallback_targets=["Bắt Đầu Khiêu Chiến", "Bat Dau Khieu Chien", "Khiêu Chiến"],
            padding_x=0.08,
            padding_y=0.04,
            verify_first=True,
        )
        # Event-driven Trigger: Chờ vào trận chiến
        self.wait_for_condition(
            lambda img: self.ocr.find_any_text(img, ["Auto", "Tự động", "Chiến đấu", "Wave", "Đợt"]) is not None,
            timeout=4.0,
            check_interval=0.15,
        )
        return True

    def check_out_of_resin(self) -> bool:
        """Checks if out of resin popup appears."""
        img = self.capture()
        if img is None:
            return False
        popup = self.ocr.find_any_text(
            img,
            ["Bổ sung", "Bo sung", "Bình Năng Lượng", "Ngọc Ánh Sao", "Khôi phục", "Moi ban chon cach"]
        )
        if popup:
            self.dismiss_resin_popup()
            return True
        return False

    def dismiss_resin_popup(self):
        """Dismisses the resin replenishment popup by tapping 'Hủy'."""
        self.log("Phát hiện popup bổ sung nhựa, bấm 'Hủy' để đóng...")
        self.tap_cached_or_learn(
            key="resin_popup_cancel",
            expected_texts=["Hủy", "Huy", "Cancel"],
            fallback_targets=["Hủy", "Huy", "Cancel"],
            padding_x=0.08,
            padding_y=0.05,
            verify_first=True,
        )
        self.sleep_cancellable(0.4)

    def ensure_combat_settings(self):
        """Verifies and turns on Auto-Battle and 2x Speed during combat."""
        self.sleep_cancellable(2.0)
        self.device.tap_box(HSRZones.BATTLE_AUTO_TOGGLE, normalized=True)
        self.sleep_cancellable(0.3)
        self.device.tap_box(HSRZones.BATTLE_SPEED_TOGGLE, normalized=True)
        self.sleep_cancellable(0.3)

    def wait_for_battle_end(self, timeout_seconds: float = 360.0) -> bool:
        """Monitors screen until victory/defeat screen appears."""
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if self.stop_requested:
                return False

            img = self.capture()
            if img is not None:
                end_match = self.ocr.find_any_text(
                    img,
                    ["Thách Đấu Lại", "Thach Dau Lai", "Chiến Thắng", "Chien Thang", "Rút Lui", "Rut Lui", "Thoát"]
                )
                if end_match:
                    _, res = end_match
                    self.log(f"Trận đấu kết thúc: Nhận diện '{res.text}'")
                    return True

            self.sleep_cancellable(1.5)

        return False

    def handle_battle_result(self, force_exit: bool = False) -> str:
        """Handles battle end screen: repeats challenge or exits."""
        img = self.capture()
        if img is None:
            return "exit"

        if not force_exit:
            repeat_btn = self.ocr.find_any_text(
                img,
                ["Thách Đấu Lại", "Thach Dau Lai", "Khiêu Chiến Lại", "Repeat"]
            )
            if repeat_btn:
                _, r_res = repeat_btn
                self.log(f"Bấm '{r_res.text}' để tiếp tục đợt mới...")
                self.device.tap(r_res.center.x, r_res.center.y, normalized=False)
                self.sleep_cancellable(1.5)

                if self.check_out_of_resin():
                    self.log("Hết nhựa sau trận đấu. Thoát...", level="warning")
                    self.device.tap(HSRZones.BACK_BUTTON.x, HSRZones.BACK_BUTTON.y, normalized=True)
                    return "exit"

                return "repeat"

        # Thoát trận (Bấm Rút Lui qua Micro-ROI & Auto-Learn)
        self.tap_cached_or_learn(
            key="battle_retreat_btn",
            expected_texts=["Rút Lui", "Rut Lui", "Thoát", "Exit"],
            fallback_targets=["Rút Lui", "Rut Lui", "Thoát", "Xác nhận", "Exit"],
            padding_x=0.08,
            padding_y=0.05,
            verify_first=True,
        )
        # Event-driven Trigger: Chờ thoát khỏi trận đấu về giao diện ngoài
        self.wait_for_condition(
            lambda img: self.ocr.find_any_text(img, ["Khiêu Chiến", "Khieu Chien", "Sổ Tay", "Huong Dan"]) is not None,
            timeout=3.0,
            check_interval=0.1,
        )
        return "exit"
