#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/backend"

if [ -f .env.example ] && [ ! -f .env ]; then
  cp .env.example .env
  echo "已复制 .env.example -> .env，请把你的 DINGTALK_APPKEY/DINGTALK_APPSECRET 填进去后再重跑。"
  exit 0
fi

echo "构建并启动 tb_tool_bt（端口 5001）..."
docker compose -f docker-compose.yml up --build
