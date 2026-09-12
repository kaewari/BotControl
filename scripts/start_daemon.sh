#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$DIR/.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "Lỗi: Không tìm thấy môi trường ảo tại $PYTHON_BIN. Hãy chạy setup trước."
    exit 1
fi

echo "========================================================="
echo "   Khởi động Unified Daemon Supervisor - BotControl     "
echo "   iPad Pro 13\" (M5) | Web Dashboard: http://localhost:8000"
echo "========================================================="

exec "$PYTHON_BIN" "$DIR/run.py" --host 0.0.0.0 --port 8000 "$@"
