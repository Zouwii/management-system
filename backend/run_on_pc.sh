#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-5001}"

USE_MYSQL="${USE_MYSQL:-1}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-tb_tool_app}"
DB_PASSWORD="${DB_PASSWORD:-123456}"
DB_NAME="${DB_NAME:-tb_tool_bt}"

INIT_MYSQL="${INIT_MYSQL:-0}"
MYSQL_ROOT_USER="${MYSQL_ROOT_USER:-root}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"

echo "[tb_tool_bt] cwd: $(pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[tb_tool_bt] ERROR: python3 not found"
  exit 1
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "[tb_tool_bt] ERROR: poetry not found"
  echo "[tb_tool_bt] Install: curl -sSL https://install.python-poetry.org | python3 -"
  echo "[tb_tool_bt] Then: export PATH=\"\$HOME/.local/bin:\$PATH\""
  exit 1
fi

if [ ! -f ".env" ]; then
  cat > .env <<EOF
DINGTALK_APPKEY=
DINGTALK_APPSECRET=
TB_TOOL_BT_DEBUG=false

TB_TOOL_BT_USE_MYSQL=${USE_MYSQL}
TB_TOOL_BT_DB_HOST=${DB_HOST}
TB_TOOL_BT_DB_PORT=${DB_PORT}
TB_TOOL_BT_DB_USER=${DB_USER}
TB_TOOL_BT_DB_PASSWORD=${DB_PASSWORD}
TB_TOOL_BT_DB_NAME=${DB_NAME}
EOF
  echo "[tb_tool_bt] Created backend/.env template (please fill DingTalk keys)."
else
  echo "[tb_tool_bt] Found backend/.env (will use it as-is)."
fi

echo "[tb_tool_bt] Installing deps (poetry install --no-root)"
poetry install --no-root

if [ "${INIT_MYSQL}" = "1" ] || [ "${INIT_MYSQL}" = "true" ] || [ "${INIT_MYSQL}" = "yes" ]; then
  echo "[tb_tool_bt] INIT_MYSQL=1, attempting to init MySQL"
  if command -v mysql >/dev/null 2>&1; then
    if [ -n "${MYSQL_ROOT_PASSWORD}" ]; then
      mysql -u"${MYSQL_ROOT_USER}" -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'%'        IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'%'        IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'%';
FLUSH PRIVILEGES;
SQL
      echo "[tb_tool_bt] MySQL init OK."
    elif command -v sudo >/dev/null 2>&1; then
      sudo mysql <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'%'        IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'%'        IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'%';
FLUSH PRIVILEGES;
SQL
      echo "[tb_tool_bt] MySQL init OK."
    else
      echo "[tb_tool_bt] ERROR: no sudo and no MYSQL_ROOT_PASSWORD provided."
      echo "[tb_tool_bt] Try: INIT_MYSQL=1 MYSQL_ROOT_PASSWORD=your_root_password bash run_on_pc.sh"
      exit 1
    fi
  else
    echo "[tb_tool_bt] ERROR: mysql client not found; cannot init MySQL automatically."
    exit 1
  fi
fi

export FLASK_RUN_HOST="${APP_HOST}"
export FLASK_RUN_PORT="${APP_PORT}"

echo "[tb_tool_bt] Starting backend: http://${APP_HOST}:${APP_PORT}"
exec poetry run python app.py

