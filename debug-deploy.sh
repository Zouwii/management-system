#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend-react"

cleanup() {
  echo ""
  echo "[dev] stopping..."
  kill $BACKEND_PID 2>/dev/null || true
  wait $BACKEND_PID 2>/dev/null || true
  kill $MCP_PID 2>/dev/null || true
  wait $MCP_PID 2>/dev/null || true
  echo "[dev] all stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

# 先释放已被占用的端口
echo "[dev] checking ports..."
fuser -k 5001/tcp 2>/dev/null || true
fuser -k 5200/tcp 2>/dev/null || true
sleep 1

# 后端
cd "${BACKEND_DIR}"
echo "[dev] backend starting..."
poetry run python3 app.py &
BACKEND_PID=$!

# 等后端就绪
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:5001/api/bt/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# MCP SSE Server
cd "${BACKEND_DIR}"
poetry run python3 -m ai.mcp --transport sse --port 5200 --host 127.0.0.1 &
MCP_PID=$!

# 前端
cd "${FRONTEND_DIR}"
echo ""
echo "============================================"
echo "  前端开发服务器已启动"
echo "  登录地址: http://localhost:5173"
echo "============================================"
echo ""
VITE_API_MODE=real npm run dev

cleanup
