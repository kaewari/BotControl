#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WDA_DIR="$DIR/WebDriverAgent"
TEAM_ID="44T7Y77WAJ"
if command -v idevice_id &> /dev/null; then
    DETECTED_ID=$(idevice_id -l | head -n 1)
fi
DEVICE_ID="${DETECTED_ID:-00008142-001C64982E09401C}"

echo "=== [1/3] Kiểm tra mã nguồn WebDriverAgent ==="
if [ ! -d "$WDA_DIR" ]; then
    echo "Đang clone Appium WebDriverAgent từ GitHub..."
    git clone https://github.com/appium/WebDriverAgent.git "$WDA_DIR"
else
    echo "Thư mục WebDriverAgent đã tồn tại tại: $WDA_DIR"
fi

cd "$WDA_DIR"

echo "=== [2/3] Cấu hình Signing Team ID: $TEAM_ID ==="
# Kiểm tra sự tồn tại của xcodebuild
if ! command -v xcodebuild &> /dev/null; then
    echo "Lỗi: Không tìm thấy xcodebuild. Hãy đảm bảo đã cài đặt Xcode."
    exit 1
fi

echo "=== [3/3] Build WebDriverAgentRunner cho iPad Pro M5 ($DEVICE_ID) ==="
echo "Quá trình build và ký chứng chỉ có thể mất 1-2 phút..."

xcodebuild build-for-testing \
    -project WebDriverAgent.xcodeproj \
    -scheme WebDriverAgentRunner \
    -destination "id=$DEVICE_ID" \
    DEVELOPMENT_TEAM="$TEAM_ID" \
    -allowProvisioningUpdates

echo "✅ Build WebDriverAgent hoàn tất thành công!"
