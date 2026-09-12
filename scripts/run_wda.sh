#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WDA_DIR="$DIR/WebDriverAgent"
TEAM_ID="N2NT9NJMU5"
DEVICE_ID="A5AE3F5C-F3CB-5152-AF24-043877300989"

if [ ! -d "$WDA_DIR" ]; then
    echo "Chưa có thư mục WebDriverAgent. Đang clone..."
    git clone --depth 1 https://github.com/appium/WebDriverAgent.git "$WDA_DIR"
fi

cd "$WDA_DIR"

# Khởi động iproxy chuyển tiếp cổng 8100 từ iPad sang localhost
if command -v iproxy &> /dev/null; then
    echo "=== Khởi động iproxy chuyển tiếp cổng 8100 từ iPad ($DEVICE_ID) ==="
    pkill -f "iproxy.*8100" 2>/dev/null || true
    iproxy 8100:8100 -u "$DEVICE_ID" > /dev/null 2>&1 &
    IPROXY_PID=$!
    echo "iproxy đang chạy ngầm (PID: $IPROXY_PID)..."
    trap "kill $IPROXY_PID 2>/dev/null || true" EXIT
fi

echo "=== Đang khởi chạy WebDriverAgentRunner trên iPad ($DEVICE_ID) ==="
echo "Nhấn Ctrl+C để dừng."

xcodebuild test-without-building \
    -project WebDriverAgent.xcodeproj \
    -scheme WebDriverAgentRunner \
    -destination "id=$DEVICE_ID" \
    -allowProvisioningUpdates 2>/dev/null || \
xcodebuild test \
    -project WebDriverAgent.xcodeproj \
    -scheme WebDriverAgentRunner \
    -destination "id=$DEVICE_ID" \
    DEVELOPMENT_TEAM="$TEAM_ID" \
    -allowProvisioningUpdates
