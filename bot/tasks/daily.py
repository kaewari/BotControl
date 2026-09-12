"""Daily tasks automation: Assignments (Ủy thác) and Daily Training rewards (Huấn luyện thường ngày)."""
import time
from bot.core.coordinates import HSRZones, BoundingBox, Point
from bot.tasks.base import BaseTask


class DailyTask(BaseTask):
    """Automates daily routine in Honkai: Star Rail."""

    def run(self, claim_assignments: bool = True, claim_training: bool = True):
        self.is_running = True
        self.stop_requested = False
        self.log("Bắt đầu chuỗi tác vụ Daily...")

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

            self.log("✅ Hoàn thành toàn bộ tác vụ Daily!")
        except Exception as e:
            self.log(f"Lỗi khi thực hiện Daily: {e}", level="error")
        finally:
            self.is_running = False

    def process_assignments(self):
        """Claims completed assignments and re-dispatches them."""
        self.log("=== [1/2] Kiểm tra Ủy Thác (Assignments) ===")

        # Đóng cửa sổ hiện tại (nếu đang ở trong Sổ tay)
        self.device.tap(HSRZones.GUIDEBOOK_CLOSE.x, HSRZones.GUIDEBOOK_CLOSE.y, normalized=True)
        self.sleep_cancellable(1.2)

        # Mở menu điện thoại (Góc trên bên trái màn hình)
        self.log("Mở menu điện thoại...")
        self.device.tap(HSRZones.PHONE_MENU_ICON.x, HSRZones.PHONE_MENU_ICON.y, normalized=True)
        self.sleep_cancellable(1.8)

        img = self.capture()
        if img is None:
            self.log("Không chụp được màn hình menu điện thoại", level="warning")
            return

        # Tìm và bấm nút 'Ủy Thác'
        uy_thac_match = self.ocr.find_any_text(
            img, 
            ["Ủy Thác", "Uy Thac", "Ủy thác", "Thác", "Thac", "Assignments"]
        )
        if uy_thac_match:
            _, res = uy_thac_match
            self.log(f"Tìm thấy '{res.text}' tại ({res.center.x:.0f}, {res.center.y:.0f}), bấm vào...")
            self.device.tap(res.center.x, res.center.y, normalized=False)
            self.sleep_cancellable(2.2)
        else:
            self.log("Không nhận diện được chữ 'Ủy Thác', dùng tọa độ cố định menu (0.887, 0.354)...")
            self.device.tap(0.887, 0.354, normalized=True)
            self.sleep_cancellable(2.2)

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
                self.sleep_cancellable(1.5)

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
                        self.sleep_cancellable(1.5)
            else:
                self.log("Chưa có ủy thác hoàn thành hoặc đã nhận trước đó.")

        # Đóng menu Ủy Thác (Bấm nút Back 2 lần)
        self.log("Đóng menu Ủy Thác...")
        self.device.tap(HSRZones.BACK_BUTTON.x, HSRZones.BACK_BUTTON.y, normalized=True)
        self.sleep_cancellable(1.0)
        self.device.tap(HSRZones.BACK_BUTTON.x, HSRZones.BACK_BUTTON.y, normalized=True)
        self.sleep_cancellable(1.2)

    def process_daily_training(self):
        """Opens Guidebook and claims daily activity points rewards."""
        self.log("=== [2/2] Nhận thưởng Huấn Luyện Thường Ngày ===")

        img = self.capture()
        if img is None:
            self.log("Không chụp được màn hình iPad", level="error")
            return

        # Kiểm tra xem đã mở Sổ tay chưa
        in_guidebook = self.ocr.find_any_text(
            img,
            ["Huong Dan Hanh Tinh", "Huong Dan Sinh Ton", "Huan Luyen Moi Ngay", "Huan Luyen"]
        )

        if not in_guidebook:
            self.log("Mở Sổ tay Hướng dẫn...")
            self.device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
            self.sleep_cancellable(2.0)
            img = self.capture()

        # Chọn tab 'Huấn Luyện Thường Ngày' (Tab 1)
        self.log("Vào tab Huấn Luyện Thường Ngày...")
        self.device.tap(HSRZones.TAB_DAILY_TRAINING.x, HSRZones.TAB_DAILY_TRAINING.y, normalized=True)
        self.sleep_cancellable(1.5)

        sub_img = self.capture()
        if sub_img is not None:
            # 1. Thu nhận tất cả các nhiệm vụ ngày đã hoàn thành (nút 'Nhận' bên dưới)
            h, w = sub_img.shape[:2]
            nhan_matches = self.ocr.find_all_text(sub_img, "Nhận")
            # Lọc các nút Nhận ở nửa dưới màn hình (y > 0.60)
            mission_claims = [r for r in nhan_matches if r.center.y > h * 0.60]
            if mission_claims:
                self.log(f"Tìm thấy {len(mission_claims)} nhiệm vụ có thể nhận thưởng...")
                for c_btn in mission_claims:
                    self.log(f"Bấm '{c_btn.text}' tại ({c_btn.center.x:.0f}, {c_btn.center.y:.0f})...")
                    self.device.tap(c_btn.center.x, c_btn.center.y, normalized=False)
                    self.sleep_cancellable(1.0)
            else:
                self.log("Không có nút 'Nhận' nhiệm vụ riêng lẻ nào.")

            # 2. Nhấp vào 5 mốc rương (100, 200, 300, 400, 500 điểm)
            self.log("Thu thập các mốc rương tích lũy 100 - 500 điểm...")
            chests_x = [0.310, 0.454, 0.598, 0.742, 0.886]
            chest_y = 0.358
            for cx in chests_x:
                self.device.tap(cx, chest_y, normalized=True)
                self.sleep_cancellable(0.5)

            # Bấm vào giữa màn hình để đóng popup nhận thưởng
            self.device.tap(0.50, 0.50, normalized=True)
            self.sleep_cancellable(0.8)

        # Đóng Sổ tay Hướng dẫn
        self.log("Đóng Sổ tay...")
        self.device.tap(HSRZones.GUIDEBOOK_CLOSE.x, HSRZones.GUIDEBOOK_CLOSE.y, normalized=True)
        self.sleep_cancellable(1.2)
