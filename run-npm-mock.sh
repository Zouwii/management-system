#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend-react"

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
  echo "[tb_tool_bt] node_modules not found, running: npm install"
  npm install
fi

echo "[tb_tool_bt] Starting frontend mock: (cd frontend-react && npm run mock)"
exec npm run mock

