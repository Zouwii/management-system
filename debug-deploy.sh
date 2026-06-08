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
  echo "[dev] all stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

# 后端
cd "${BACKEND_DIR}"
echo "[dev] starting backend (port 5001)..."
python app.py &
BACKEND_PID=$!

# 等后端就绪
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:5001/api/bt/health >/dev/null 2>&1; then
    echo "[dev] backend ready."
    break
  fi
  sleep 1
done

# 前端
cd "${FRONTEND_DIR}"
echo "[dev] starting frontend (port 5173)..."
VITE_API_MODE=real npm run dev

cleanup
