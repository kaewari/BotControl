#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WDA_DIR="$DIR/WebDriverAgent"
TEAM_ID="N2NT9NJMU5"
DEVICE_ID="A5AE3F5C-F3CB-5152-AF24-043877300989"
PYTHON_BIN="$DIR/.venv/bin/python"

if [ ! -d "$WDA_DIR" ]; then
    echo "Chưa có thư mục WebDriverAgent. Hãy chạy scripts/setup_wda.sh trước."
    exit 1
fi

cd "$WDA_DIR"

echo "=== Đang khởi chạy WebDriverAgentRunner trên iPad ($DEVICE_ID) ==="
echo "Nhấn Ctrl+C để dừng."

# Khởi chạy test-without-building (nếu đã build) hoặc test
xcodebuild test-without-building \
    -project WebDriverAgent.xcodeproj \
    -scheme WebDriverAgentRunner \
    -destination "id=$DEVICE_ID" \
    -allowProvisioningUpdates || \
xcodebuild test \
    -project WebDriverAgent.xcodeproj \
    -scheme WebDriverAgentRunner \
    -destination "id=$DEVICE_ID" \
    DEVELOPMENT_TEAM="$TEAM_ID" \
    -allowProvisioningUpdates
