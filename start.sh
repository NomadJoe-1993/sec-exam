#!/usr/bin/env bash
# 证从刷题 · 后端启动脚本
# 用于生产环境部署

set -e
cd "$(dirname "$0")"

# 配置
HOST="0.0.0.0"
PORT=5000
WORKERS=2
VENV_DIR="$(dirname "$0")/.venv"

# 检测虚拟环境
if [ ! -f "$VENV_DIR/bin/python" ]; then
  echo "📦 首次运行：创建虚拟环境..."
  uv venv "$VENV_DIR"
  "$VENV_DIR/bin/uv" pip install flask flask-cors gunicorn
fi

# 启动
echo "📚 证从刷题 · 会员后端"
echo "   端口: $HOST:$PORT"
echo "   管理面板: http://$HOST:$PORT/admin"
echo ""
exec "$VENV_DIR/bin/gunicorn" \
  --bind "$HOST:$PORT" \
  --workers $WORKERS \
  --access-logfile - \
  --error-logfile - \
  --timeout 30 \
  "backend.app:app"
