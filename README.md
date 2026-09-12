# BotControl - Tự Động Hóa Honkai: Star Rail trên iPad Pro 13" (M5)

Hệ thống bot tự động hóa chơi game **Honkai: Star Rail** (bản Tiếng Việt) trên **iPad Pro 13-inch (M5)** được điều khiển trực tiếp từ máy Mac qua cáp USB-C bằng **WebDriverAgent** và **Thị giác máy tính (OpenCV + RapidOCR Tiếng Việt)**.

---

## 🌟 Tính Năng Chính (Giai đoạn 1)

1. **🌾 Tự Động Xả Nhựa (Sức Mạnh Khai Phá)**:
   - Tự động mở Sổ Tay Hướng Dẫn -> Chỉ Số Sinh Tồn.
   - Hỗ trợ farm:
     - **Đài Hoa Nhân Tạo (Vàng)**: EXP nhân vật, Điểm Tín Dụng, EXP Nón Ánh Sáng.
     - **Đài Hoa Nhân Tạo (Đỏ)**: Nguyên liệu Vết Tích theo Vận Mệnh.
     - **Vết Tích Xâm Thực**: Farm Di Vật.
     - **Bóng Hình Ngưng Trệ**: Nguyên liệu đột phá.
     - **Dư Âm Chiến Đấu**: Boss Tuần.
   - Tự động chỉnh số đợt khiêu chiến (1 đến 6 đợt).
   - Tự động kích hoạt **Chiến đấu tự động (Auto Battle)** & **Tốc độ x2**.
   - Tự động nhận diện kết thúc trận (Chiến thắng) và bấm **Thách đấu lại** cho đến khi hết lượt hoặc hết nhựa.

2. **📅 Tự Động Làm Daily Routine**:
   - Nhận và phái lại toàn bộ **Ủy Thác (Assignments)** chỉ với 1 click.
   - Nhận thưởng toàn bộ mốc **Huấn Luyện Thường Ngày** (500 điểm = 60 Ngọc Ánh Sao).

3. **⏩ Tự Động Tua Nhanh & Skip Hội Thoại (Dialogue Fast-Forward)**:
   - Tự động nhấp liên tục vào khu vực an toàn để tua nhanh lời thoại NPC.
   - Tự động phát hiện nút **Bỏ qua (Skip)** ở góc trên bên phải màn hình và bấm Xác nhận bỏ qua.
   - Tự động chọn câu trả lời đầu tiên khi có lựa chọn đối thoại.

4. **🖥️ Web Dashboard Trực Quan (Local Web UI)**:
   - **Live Stream MJPEG**: Xem trực tiếp màn hình iPad thời gian thực trên trình duyệt máy Mac.
   - **Click-to-Touch**: Nhấp chuột trực tiếp vào khung video stream trên web để chạm cảm ứng lên màn hình iPad.
   - **Quản lý tác vụ**: Chọn nhiệm vụ, số lần chạy, tạm dừng, dừng khẩn cấp.
   - **Console Log thời gian thực**: WebSocket cập nhật từng thao tác của bot kèm timestamp.

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### Bước 1: Thiết lập Chế độ Nhà phát triển trên iPad Pro M5
1. Trên iPad, vào **Cài đặt (Settings) -> Quyền riêng tư & Bảo mật (Privacy & Security) -> Chế độ nhà phát triển (Developer Mode) -> Bật (On)**.
2. Khởi động lại iPad theo yêu cầu của hệ thống.
3. Cắm cáp USB-C nối iPad với máy Mac. Màn hình iPad hiện thông báo -> chọn **Tin cậy máy tính này (Trust This Computer)** và nhập passcode của iPad.

### Bước 2: Khởi chạy WebDriverAgentRunner trên iPad
Mở một cửa sổ Terminal mới trên Mac và chạy:
```bash
./scripts/run_wda.sh
```
*Lưu ý lần đầu tiên:* Trên iPad có thể xuất hiện thông báo nhà phát triển chưa được tin cậy. Vào **Cài đặt (Settings) -> Cài đặt chung (General) -> Quản lý VPN & Thiết bị (VPN & Device Management)** -> Chọn chứng chỉ `sonhoang1653@gmail.com` -> Bấm **Tin cậy (Trust)**.

Sau khi khởi chạy thành công, WDA sẽ lắng nghe lệnh tại `http://localhost:8100`.

### Bước 3: Mở Web Dashboard điều khiển Bot
Mở một cửa sổ Terminal khác và chạy:
```bash
./scripts/start_dashboard.sh
```
Truy cập trình duyệt tại: **[http://localhost:8000](http://localhost:8000)**.

---

## ⚙️ Cấu Trúc Mã Nguồn

```
BotControl/
├── config.yaml               # File cấu hình thiết bị, tham số bot và web
├── requirements.txt          # Các thư viện Python phụ thuộc
├── run.py                    # Điểm khởi chạy chính (hỗ trợ cả Web Dashboard & CLI)
├── scripts/
│   ├── setup_wda.sh          # Tải và build WebDriverAgent cho iPad Pro M5
│   ├── run_wda.sh            # Khởi chạy WDA Runner trên iPad qua USB
│   └── start_dashboard.sh    # Khởi chạy Web Dashboard server
├── bot/
│   ├── core/
│   │   ├── coordinates.py    # Hệ tọa độ chuẩn hóa, vùng bấm HSRZones
│   │   └── device.py         # Kết nối WDA, chụp màn hình, gửi lệnh tap/swipe
│   ├── cv/
│   │   ├── ocr_service.py    # RapidOCR tiếng Việt, chuẩn hóa ký tự, fuzzy matching
│   │   └── matcher.py        # OpenCV template matching đa tỉ lệ
│   ├── tasks/
│   │   ├── base.py           # BaseTask quản lý vòng đời, sleep_cancellable, log
│   │   ├── daily.py          # Tự động nhận ủy thác và điểm năng động
│   │   ├── resin.py          # Tự động xả nhựa Calyx, Di vật, Boss tuần
│   │   └── dialogue.py       # Tự động tua và skip hội thoại cốt truyện
│   └── web/
│       ├── server.py         # FastAPI backend, MJPEG live stream, WebSockets
│       └── static/
│           ├── index.html    # Giao diện Web Dashboard Dark Mode
│           ├── style.css     # Thiết kế giao diện hiện đại
│           └── app.js        # Logic điều khiển và click-to-touch
└── tests/                    # Bộ kiểm thử tự động
```

---

## 🧪 Chạy Kiểm Thử Hệ Thống (Unit Tests)

```bash
.venv/bin/python -m unittest discover tests
```
Tất cả các bài test kiểm tra hệ tọa độ, nhận diện chữ tiếng Việt qua OCR, và các API endpoints của server đều đã được xác thực thành công.
