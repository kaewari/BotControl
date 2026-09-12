"""Daily tasks automation: Assignments (Ủy thác) and Daily Training rewards (Huấn luyện thường ngày)."""
import time
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.core.cache import ui_cache
from bot.tasks.base import BaseTask


class DailyTask(BaseTask):
    """Automates daily routine in Honkai: Star Rail with persistent coordinate caching."""

    def run(self, claim_assignments: bool = True, claim_training: bool = True):
        self.is_running = True
        self.stop_requested = False
        self.log("Bắt đầu chuỗi tác vụ Daily (Chế độ Tốc Độ Cao & Cache)...")

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
        """Claims completed assignments and re-dispatches them using fast cache."""
        self.log("=== [1/2] Kiểm tra Ủy Thác (Assignments) ===")

        # Đóng cửa sổ hiện tại nếu có
        close_pt = ui_cache.get_point("guidebook_close") or HSRZones.GUIDEBOOK_CLOSE
        self.device.tap(close_pt.x, close_pt.y, normalized=True)
        self.sleep_cancellable(0.8)

        # Mở menu điện thoại (Góc trên bên trái màn hình)
        self.log("Mở menu điện thoại...")
        phone_pt = ui_cache.get_point("phone_menu_icon") or HSRZones.PHONE_MENU_ICON
        self.device.tap(phone_pt.x, phone_pt.y, normalized=True)
        self.sleep_cancellable(1.2)

        # Fast-Path: Bấm trực tiếp nút 'Ủy Thác' từ cache
        assign_pt = ui_cache.get_point("phone_assignments") or Point(0.887, 0.354)
        self.log(f"Fast-Path: Bấm nút 'Ủy Thác' tại ({assign_pt.x:.3f}, {assign_pt.y:.3f})...")
        self.device.tap(assign_pt.x, assign_pt.y, normalized=True)
        self.sleep_cancellable(1.5)

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
                self.sleep_cancellable(1.0)

                # Bấm 'Phái lại tất cả' / 'Phái lại'
                re_img = self.capture()
                if re_img is not None:
                    redispatch = self.ocr.find_any_text(
                        re_img,
                        ["Phái lại", "Phai lai", "Phái lại tất cả", "Dispatch Again", "Xác nhận"]
                    )
                    if redispatch:
                        _, r_res = redispatch
                        self.log(f"Bấm '{r_res.text}' để tiếp tục gửi...")
                        self.device.tap(r_res.center.x, r_res.center.y, normalized=False)
                        self.sleep_cancellable(1.0)
            else:
                self.log("Chưa có ủy thác hoàn thành hoặc đã nhận trước đó.")

        # Đóng menu Ủy Thác (Bấm nút Close / Back)
        self.log("Đóng menu Ủy Thác...")
        self.device.tap(close_pt.x, close_pt.y, normalized=True)
        self.sleep_cancellable(0.8)
        self.device.tap(0.20, 0.85, normalized=True)  # Đóng menu điện thoại về overworld
        self.sleep_cancellable(0.8)

    def process_daily_training(self):
        """Opens Guidebook and claims daily activity points rewards with fast cache."""
        self.log("=== [2/2] Nhận thưởng Huấn Luyện Thường Ngày ===")

        # Mở Sổ tay Hướng dẫn qua cache
        guide_pt = ui_cache.get_point("guidebook_icon") or HSRZones.GUIDEBOOK_ICON
        self.log("Mở Sổ tay Hướng dẫn...")
        self.device.tap(guide_pt.x, guide_pt.y, normalized=True)
        self.sleep_cancellable(1.5)

        # Chọn tab 'Huấn Luyện Thường Ngày' (Tab 1)
        tab_pt = ui_cache.get_point("tab_daily_training") or HSRZones.TAB_DAILY_TRAINING
        self.log("Vào tab Huấn Luyện Thường Ngày...")
        self.device.tap(tab_pt.x, tab_pt.y, normalized=True)
        self.sleep_cancellable(1.0)

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
                    self.sleep_cancellable(0.6)

            # 2. Nhấp nhanh vào 5 mốc rương (100, 200, 300, 400, 500 điểm) qua cache
            self.log("Fast-Chain: Thu thập các mốc rương tích lũy 100 - 500 điểm...")
            chest_keys = ["chest_100", "chest_200", "chest_300", "chest_400", "chest_500"]
            for ck in chest_keys:
                c_pt = ui_cache.get_point(ck)
                if c_pt:
                    self.device.tap(c_pt.x, c_pt.y, normalized=True)
                    self.sleep_cancellable(0.20, step=0.05)

            # Bấm vào giữa màn hình để đóng popup nhận thưởng
            self.device.tap(0.50, 0.50, normalized=True)
            self.sleep_cancellable(0.5)

        # Đóng Sổ tay Hướng dẫn
        self.log("Đóng Sổ tay...")
        close_pt = ui_cache.get_point("guidebook_close") or HSRZones.GUIDEBOOK_CLOSE
        self.device.tap(close_pt.x, close_pt.y, normalized=True)
        self.sleep_cancellable(0.8)
