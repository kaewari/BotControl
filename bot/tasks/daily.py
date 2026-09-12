"""Daily tasks automation: Assignments (Ủy thác) and Daily Training rewards (Huấn luyện thường ngày)."""
import time
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.core.cache import ui_cache
from bot.tasks.base import BaseTask


class DailyTask(BaseTask):
    """Automates daily routine in Honkai: Star Rail with persistent coordinate caching,
    Micro-ROI verification, self-healing auto-learn, and event-driven screen state triggers."""

    def run(self, claim_assignments: bool = True, claim_training: bool = True):
        self.is_running = True
        self.stop_requested = False
        self.log("Bắt đầu chuỗi tác vụ Daily (Event-Driven & Micro-ROI Self-Healing)...")

        # 0. Kiểm tra kết nối thiết bị
        if not self.device.check_connection():
            self.log("LỖI: WDA chưa kết nối tới iPad! Vui lòng kiểm tra lại cáp và WDA.", level="error")
            self.is_running = False
            return

        try:
            # 1. Quản lý Ủy Thác (Assignments)
            if claim_assignments and not self.stop_requested:
                self.process_assignments()

            # 2. Nhận thưởng Huấn Luyện Thường Ngày (Daily Training)
            if claim_training and not self.stop_requested:
                self.process_daily_training()

            self.log("✅ Hoàn thành toàn bộ tác vụ Daily siêu tốc!")
        except Exception as e:
            self.log(f"Lỗi khi thực hiện Daily: {e}", level="error")
        finally:
            self.is_running = False

    def process_assignments(self):
        """Claims completed assignments and re-dispatches them using fast cache & event triggers."""
        self.log("=== [1/2] Kiểm tra Ủy Thác (Assignments) ===")

        # Đóng cửa sổ hiện tại nếu có
        close_pt = ui_cache.get_point("guidebook_close") or HSRZones.GUIDEBOOK_CLOSE
        self.device.tap(close_pt.x, close_pt.y, normalized=True)
        self.sleep_cancellable(0.3)

        # Mở menu điện thoại (Góc trên bên trái màn hình)
        self.log("Mở menu điện thoại...")
        self.tap_cached_or_learn("phone_menu_icon", verify_first=False)

        # Event-driven Trigger: Chờ menu điện thoại mở ra (Micro-ROI kiểm tra mục Ủy Thác)
        assign_pt = ui_cache.get_point("phone_assignments") or Point(0.887, 0.354)
        assign_roi = BoundingBox(max(0.0, assign_pt.x - 0.08), max(0.0, assign_pt.y - 0.05), min(1.0, assign_pt.x + 0.08), min(1.0, assign_pt.y + 0.05))
        self.wait_for_roi_text(assign_roi, ["Ủy Thác", "Thác", "Uy Thac", "Thac", "Dispatch"], timeout=1.5, check_interval=0.05)

        if self.stop_requested:
            return

        # Fast-Path + Micro-ROI + Auto-Learn: Bấm nút 'Ủy Thác'
        self.tap_cached_or_learn(
            key="phone_assignments",
            expected_texts=["Ủy Thác", "Thác", "Uy Thac", "Thac", "Dispatch"],
            fallback_targets=["Ủy Thác", "Uy Thac", "Thác", "Thac"],
            padding_x=0.07,
            padding_y=0.04,
            verify_first=True,
        )

        if self.stop_requested:
            return

        # Tìm nút 'Nhận tất cả' hoặc 'Thu nhận' hoặc 'Nhận'
        assign_img = self.capture()
        if assign_img is not None:
            claim_all = self.ocr.find_any_text(
                assign_img,
                ["Nhận tất cả", "Nhan tat ca", "Thu nhận", "Nhận", "Claim All", "Claim"]
            )
            if claim_all:
                _, c_res = claim_all
                self.log(f"Bấm '{c_res.text}'...")
                self.device.tap(c_res.center.x, c_res.center.y, normalized=False)

                # Event-driven Trigger: Chờ nút 'Phái lại tất cả' xuất hiện
                redispatch_match = self.wait_for_any_text(
                    ["Phái lại", "Phai lai", "Phái lại tất cả", "Dispatch Again", "Xác nhận"],
                    timeout=1.5,
                    check_interval=0.05,
                )
                if redispatch_match:
                    _, r_res = redispatch_match
                    self.log(f"Bấm '{r_res.text}' để tiếp tục gửi...")
                    self.device.tap(r_res.center.x, r_res.center.y, normalized=False)
                    self.sleep_cancellable(0.2)
            else:
                self.log("Chưa có ủy thác hoàn thành hoặc đã nhận trước đó.")

        if self.stop_requested:
            return

        # Đóng menu Ủy Thác (Bấm nút Close / Back)
        self.log("Đóng menu Ủy Thác...")
        self.tap_cached_or_learn("guidebook_close", verify_first=False)
        self.sleep_cancellable(0.15)
        self.device.tap(0.20, 0.85, normalized=True)  # Đóng menu điện thoại về overworld
        self.sleep_cancellable(0.15)

    def process_daily_training(self):
        """Opens Guidebook and claims daily activity points rewards with Fast-Path & Event Triggers."""
        self.log("=== [2/2] Nhận thưởng Huấn Luyện Thường Ngày ===")

        if self.stop_requested:
            return

        # Mở Sổ tay Hướng dẫn qua cache
        self.log("Mở Sổ tay Hướng dẫn...")
        self.tap_cached_or_learn("guidebook_icon", verify_first=False)

        # Event-driven Trigger: Chờ Sổ Tay xuất hiện (Micro-ROI kiểm tra tab Huấn Luyện Thường Ngày)
        tab_pt = ui_cache.get_point("tab_daily_training") or Point(0.150, 0.245)
        tab_roi = BoundingBox(max(0.0, tab_pt.x - 0.09), max(0.0, tab_pt.y - 0.06), min(1.0, tab_pt.x + 0.09), min(1.0, tab_pt.y + 0.06))
        self.wait_for_roi_text(tab_roi, ["Huấn Luyện", "Huan Luyen", "Thường Ngày", "Thuong Ngay", "Mỗi Ngày", "Moi Ngay"], timeout=1.5, check_interval=0.05)

        if self.stop_requested:
            return

        # Chọn tab 'Huấn Luyện Thường Ngày' (Tab 1) với Micro-ROI & Auto-Learn
        self.log("Vào tab Huấn Luyện Thường Ngày...")
        self.tap_cached_or_learn(
            key="tab_daily_training",
            expected_texts=["Huấn Luyện", "Huan Luyen", "Mỗi Ngày", "Moi Ngay", "Daily"],
            fallback_targets=["Huấn Luyện", "Huan Luyen", "Mỗi Ngày", "Moi Ngay"],
            padding_x=0.06,
            padding_y=0.04,
            verify_first=True,
        )

        if self.stop_requested:
            return

        sub_img = self.capture()
        if sub_img is not None:
            # 1. Thu nhận tất cả các nhiệm vụ ngày đã hoàn thành (nút 'Nhận' bên dưới)
            h, w = sub_img.shape[:2]
            nhan_matches = self.ocr.find_all_text(sub_img, "Nhận")
            mission_claims = [r for r in nhan_matches if r.center.y > h * 0.60]
            if mission_claims:
                self.log(f"Tìm thấy {len(mission_claims)} nhiệm vụ có thể nhận thưởng...")
                for c_btn in mission_claims:
                    self.device.tap(c_btn.center.x, c_btn.center.y, normalized=False)
                    self.sleep_cancellable(0.20)

            # 2. Nhấp nhanh vào 5 mốc rương (100, 200, 300, 400, 500 điểm) qua cache
            self.log("Fast-Chain: Thu thập các mốc rương tích lũy 100 - 500 điểm...")
            chest_keys = ["chest_100", "chest_200", "chest_300", "chest_400", "chest_500"]
            for ck in chest_keys:
                c_pt = ui_cache.get_point(ck)
                if c_pt:
                    self.device.tap(c_pt.x, c_pt.y, normalized=True)
                    self.sleep_cancellable(0.10, step=0.02)

            # Bấm vào giữa màn hình để đóng popup nhận thưởng
            self.device.tap(0.50, 0.50, normalized=True)
            self.sleep_cancellable(0.2)

        # Đóng Sổ tay Hướng dẫn
        self.log("Đóng Sổ tay...")
        self.tap_cached_or_learn("guidebook_close", verify_first=False)
        self.sleep_cancellable(0.3)
