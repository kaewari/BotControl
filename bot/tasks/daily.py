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

        # Bước 1: Mở menu điện thoại (Góc trên bên trái màn hình)
        self.log("Mở menu điện thoại...")
        self.device.tap(0.04, 0.05, normalized=True)
        self.sleep_cancellable(1.5)

        img = self.capture()
        if img is None:
            self.log("Không chụp được màn hình menu", level="warning")
            return

        # Bước 2: Tìm và bấm nút 'Ủy Thác'
        uy_thac_match = self.ocr.find_any_text(img, ["Ủy Thác", "Uy Thac", "Assignments"])
        if uy_thac_match:
            _, res = uy_thac_match
            self.log(f"Tìm thấy '{res.text}', bấm vào...")
            self.device.tap(res.center.x, res.center.y, normalized=False)
            self.sleep_cancellable(2.0)

            # Bước 3: Tìm nút 'Nhận tất cả' hoặc 'Thu nhận'
            assign_img = self.capture()
            if assign_img is not None:
                claim_all = self.ocr.find_any_text(
                    assign_img,
                    ["Nhận tất cả", "Nhan tat ca", "Thu nhận", "Claim All"]
                )
                if claim_all:
                    _, c_res = claim_all
                    self.log(f"Bấm '{c_res.text}'...")
                    self.device.tap(c_res.center.x, c_res.center.y, normalized=False)
                    self.sleep_cancellable(1.5)

                    # Bước 4: Tìm nút 'Phái lại tất cả' / 'Phái lại'
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

            # Trở về màn hình chính (Bấm nút Back ở góc trên bên trái)
            self.log("Đóng menu Ủy Thác...")
            self.device.tap(0.04, 0.05, normalized=True)
            self.sleep_cancellable(1.0)
            self.device.tap(0.04, 0.05, normalized=True)
            self.sleep_cancellable(1.2)
        else:
            self.log("Không tìm thấy mục 'Ủy Thác' trong menu điện thoại", level="warning")
            # Thoát menu
            self.device.tap(0.04, 0.05, normalized=True)
            self.sleep_cancellable(1.0)

    def process_daily_training(self):
        """Opens Guidebook and claims daily activity points rewards."""
        self.log("=== [2/2] Nhận thưởng Huấn Luyện Thường Ngày ===")

        # Mở Sổ tay Hướng dẫn (Biểu tượng cuốn sách góc trên bên phải)
        self.log("Mở Sổ tay Hướng dẫn...")
        self.device.tap_box(HSRZones.GUIDEBOOK_ICON, normalized=True)
        self.sleep_cancellable(2.0)

        img = self.capture()
        if img is None:
            return

        # Chọn tab 'Huấn Luyện Thường Ngày'
        tab_match = self.ocr.find_any_text(
            img,
            ["Huấn Luyện Thường Ngày", "Huan Luyen", "Daily Training"]
        )
        if tab_match:
            _, t_res = tab_match
            self.log(f"Vào tab '{t_res.text}'...")
            self.device.tap(t_res.center.x, t_res.center.y, normalized=False)
            self.sleep_cancellable(1.5)

            # Bấm 'Nhận tất cả' nếu có
            sub_img = self.capture()
            if sub_img is not None:
                claim_btn = self.ocr.find_any_text(
                    sub_img,
                    ["Nhận tất cả", "Nhan tat ca", "Nhận", "Claim"]
                )
                if claim_btn:
                    _, btn_res = claim_btn
                    self.log(f"Bấm '{btn_res.text}' nhận thưởng năng động...")
                    self.device.tap(btn_res.center.x, btn_res.center.y, normalized=False)
                    self.sleep_cancellable(1.5)
                else:
                    self.log("Đã nhận hết điểm huấn luyện hoặc chưa đạt mốc mới.")

        # Đóng Sổ tay Hướng dẫn (Bấm Back góc trên trái hoặc nút thoát góc trên phải)
        self.log("Đóng Sổ tay Hướng dẫn...")
        self.device.tap(0.04, 0.05, normalized=True)
        self.sleep_cancellable(1.5)
