#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"
FRONTEND_DIR="${SCRIPT_DIR}/frontend-react"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-5001}"

# 杀掉旧进程，等待端口释放
OLD_PID=$(lsof -ti :"$APP_PORT" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  echo "[tb_tool_bt] Killing old process PID=$OLD_PID on port $APP_PORT"
  kill "$OLD_PID" 2>/dev/null || true
  for i in $(seq 1 10); do
    if ! lsof -ti :"$APP_PORT" >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi

MODE_ARG="${1:-mode=1}"

# mode=1(默认): real 登录页（钉钉）
# mode=2: mock 登录页（账号密码）
if [[ "${MODE_ARG}" =~ ^mode= ]]; then
  MODE="${MODE_ARG#mode=}"
else
  MODE="${MODE_ARG}"
fi

case "${MODE}" in
  1)
    FRONTEND_API_MODE="real"
    ;;
  2)
    FRONTEND_API_MODE="mock"
    ;;
  *)
    echo "[tb_tool_bt] ERROR: invalid mode: ${MODE_ARG}"
    echo "[tb_tool_bt] Usage: bash run-backend-poetry-app.sh [mode=1|mode=2]"
    echo "[tb_tool_bt]   mode=1 => real (DingTalk login)"
    echo "[tb_tool_bt]   mode=2 => mock (account/password login)"
    exit 1
    ;;
esac

if ! command -v npm >/dev/null 2>&1; then
  echo "[tb_tool_bt] ERROR: npm not found"
  echo "[tb_tool_bt] Please install Node.js and npm first."
  exit 1
fi

if [ ! -d "${FRONTEND_DIR}" ]; then
  echo "[tb_tool_bt] ERROR: frontend directory not found: ${FRONTEND_DIR}"
  exit 1
fi

cd "${FRONTEND_DIR}"

if [ ! -d node_modules ] || [ ! -x "node_modules/.bin/vite" ]; then
  echo "[tb_tool_bt] frontend dependencies missing/incomplete, running install"
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
fi

echo "[tb_tool_bt] Building frontend mode=${MODE} (VITE_API_MODE=${FRONTEND_API_MODE})"
VITE_API_MODE="${FRONTEND_API_MODE}" npm run build

cd "$BACKEND_DIR"

if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  echo "[tb_tool_bt] Copied backend/.env.example -> backend/.env (please fill DingTalk keys if needed)."
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "[tb_tool_bt] ERROR: poetry not found"
  echo "[tb_tool_bt] Please install Poetry, e.g.: curl -sSL https://install.python-poetry.org | python3 -"
  exit 1
fi

export FLASK_RUN_HOST="${APP_HOST}"
export FLASK_RUN_PORT="${APP_PORT}"
export AI_TTYD_BASE_URL="${AI_TTYD_BASE_URL:-http://127.0.0.1:{port}/}"
export AI_TTYD_PORT_BASE="${AI_TTYD_PORT_BASE:-8800}"
export AI_TTYD_PORT_SPAN="${AI_TTYD_PORT_SPAN:-400}"

echo "[tb_tool_bt] Starting backend: http://${APP_HOST}:${APP_PORT} (frontend mode=${MODE})"
echo "[tb_tool_bt] AI ttyd base: ${AI_TTYD_BASE_URL} (base=${AI_TTYD_PORT_BASE}, span=${AI_TTYD_PORT_SPAN})"
exec poetry run python app.py

