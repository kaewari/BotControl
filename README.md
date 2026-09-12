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

## ⚙️ Cấu Trúc Thư Mục Chuẩn Software Development

```text
BotControl/
├── assets/                           # Tài nguyên hình ảnh, media & asset kiểm thử
│   └── screenshots/                  # Ảnh chụp màn hình iPad thật & audit log
│       ├── audit_current_screen.png
│       ├── live_screen.png
│       ├── real_ipad_screen.png
│       └── uy_thac_screen.png
├── docs/                             # Tài liệu kỹ thuật chuyên sâu & hướng dẫn
│   ├── audit_bug_log.md              # Nhật ký kiểm định lỗi thời gian thực (Live Bug Audit)
│   └── TEST_READY.md                 # Hướng dẫn sẵn sàng kiểm thử phần cứng iPad Pro M5
├── data/                             # Dữ liệu vận hành & bộ nhớ đệm cục bộ
│   └── ui_cache.json                 # Bộ nhớ đệm tọa độ chuẩn hóa & bounding box UI
├── bot/                              # Gói mã nguồn ứng dụng chính (Application Package)
│   ├── core/                         # Module lõi hệ thống
│   │   ├── cache.py                  # Persistent UI cache, micro-ROI verification & self-healing
│   │   ├── coordinates.py            # Hệ tọa độ chuẩn hóa, vùng bấm HSRZones
│   │   ├── device.py                 # Điều khiển phần cứng, WDA socket reader, frame producer
│   │   ├── human_touch.py            # Mô phỏng sinh học 2D Gaussian, Bezier swipe, Captcha failsafe
│   │   ├── resource_guard.py         # Zero-Spend ResourceGuard, reflex cancel <0.5s, pre-tap veto
│   │   └── trigger.py                # ScreenStateTrigger phản xạ vi tuần hoàn, FreshFrameGuard
│   ├── cv/                           # Module thị giác máy tính & nhận diện
│   │   ├── matcher.py                # OpenCV template matching đa tỉ lệ
│   │   └── ocr_service.py            # RapidOCR tiếng Việt, chuẩn hóa ký tự, single-pass OCR
│   ├── tasks/                        # Các tác vụ tự động hóa game
│   │   ├── base.py                   # BaseTask quản lý vòng đời, cognitive pause, log
│   │   ├── daily.py                  # Tự động nhận ủy thác và điểm năng động
│   │   ├── dialogue.py               # Tự động tua và skip hội thoại cốt truyện
│   │   ├── fast_chain.py             # FastChainExecutor chuỗi tương tác siêu tốc
│   │   ├── resin.py                  # Tự động xả nhựa Calyx, Di vật, Boss tuần
│   │   ├── simulated_universe.py     # Tự động Vũ trụ Sai phân & Vũ trụ Mô phỏng
│   │   └── smart_pipeline.py         # Lộ trình hợp nhất tối ưu Smart-Pipeline 3 pha
│   └── web/                          # Giao diện Web Dashboard & WebSocket streaming
│       ├── server.py                 # FastAPI backend, 60 FPS WebSocket stream, REST API
│       └── static/                   # Static assets: HTML5 Canvas, Dark Mode UI, app.js
├── scripts/                          # Script bash điều khiển thiết bị & cài đặt
│   ├── check_device.sh               # Kiểm tra kết nối USB và nhận diện iPad M5
│   ├── inspect_live_ui.py            # Script soi tọa độ và OCR trực tiếp
│   ├── run_wda.sh                    # Khởi chạy WDA Runner trên iPad qua USB
│   ├── run_wda_real_device.sh        # Khởi chạy WDA trên thiết bị vật lý
│   └── setup_env.sh                  # Cài đặt môi trường ảo và dependencies
├── tests/                            # Bộ kiểm thử tự động toàn diện (Unit, Integration, Benchmark)
│   ├── mock_wda.py                   # Mock harness mô phỏng WDA không can thiệp phần cứng
│   ├── test_cache.py                 # Kiểm thử UI Cache & Micro-ROI Self-Healing
│   ├── test_coordinates.py           # Kiểm thử hệ tọa độ chuẩn hóa
│   ├── test_daily_speed.py           # Benchmark tốc độ tác vụ Daily
│   ├── test_fast_chain.py            # Kiểm thử chuỗi thao tác nhanh Fast-Chain
│   ├── test_human_touch.py           # Kiểm thử phân phối 2D Gaussian & Bezier
│   ├── test_ocr.py                   # Kiểm thử OCR tiếng Việt
│   ├── test_resource_guard.py        # Kiểm thử bộ bảo vệ tài nguyên Zero-Spend
│   ├── test_resource_guard_adversarial.py # Kiểm thử tấn công từ khóa nhạy cảm đa luồng
│   ├── test_resource_guard_stress.py # Kiểm thử áp lực 100 lần độ trễ phản xạ hủy <0.5s
│   ├── test_server.py                # Kiểm thử API Web Server
│   ├── test_smart_pipeline_benchmark.py # Benchmark 10 vòng lộ trình Smart-Pipeline
│   ├── test_stream.py                # Kiểm thử luồng phát video WebSocket 60 FPS
│   └── test_trigger.py               # Kiểm thử bộ kích hoạt phản xạ ScreenStateTrigger
├── WebDriverAgent/                   # XCUITest driver cho iPadOS
├── config.yaml                       # File cấu hình thiết bị, tham số bot và web
├── requirements.txt                  # Các thư viện Python phụ thuộc
├── run.py                            # Điểm khởi chạy chính (CLI entrypoint & Web Server)
├── README.md                         # Tài liệu giới thiệu tổng quan dự án
└── .gitignore                        # Cấu hình loại trừ file git
```

---

## 🧪 Chạy Kiểm Thử Hệ Thống (Unit Tests)

```bash
.venv/bin/python -m unittest discover tests
```
Tất cả các bài test kiểm tra hệ tọa độ, nhận diện chữ tiếng Việt qua OCR, và các API endpoints của server đều đã được xác thực thành công.
