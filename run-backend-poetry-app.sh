#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"

cd "$BACKEND_DIR"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-5001}"

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

echo "[tb_tool_bt] Starting backend: http://${APP_HOST}:${APP_PORT}"
exec poetry run python app.py

