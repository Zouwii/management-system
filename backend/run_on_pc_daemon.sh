#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-5002}"
# 对外访问地址（用于日志展示，不影响监听）
APP_PUBLIC_HOST="${APP_PUBLIC_HOST:-172.19.3.79}"

USE_MYSQL="${USE_MYSQL:-1}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-tb_tool_app}"
DB_PASSWORD="${DB_PASSWORD:-123456}"
DB_NAME="${DB_NAME:-tb_management}"

INIT_MYSQL="${INIT_MYSQL:-0}"
MYSQL_ROOT_USER="${MYSQL_ROOT_USER:-root}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"

DAEMON_NAME="${DAEMON_NAME:-tb_tool_bt_daemon}"
RUNTIME_DIR="${RUNTIME_DIR:-$(pwd)/runtime}"
PID_FILE="${PID_FILE:-${RUNTIME_DIR}/${DAEMON_NAME}.pid}"
LOG_FILE="${LOG_FILE:-${RUNTIME_DIR}/${DAEMON_NAME}.log}"
USE_POETRY=0

mkdir -p "${RUNTIME_DIR}"

is_running() {
  if [ -f "${PID_FILE}" ]; then
    local pid
    pid="$(cat "${PID_FILE}")"
    if [ -n "${pid}" ] && kill -0 "${pid}" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

ensure_prerequisites() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[tb_tool_bt] ERROR: python3 not found"
    exit 1
  fi

  # Poetry 通常安装在 ~/.local/bin，守护进程/非交互 shell 下 PATH 里可能没有。
  export PATH="$HOME/.local/bin:$PATH"

  if command -v poetry >/dev/null 2>&1; then
    USE_POETRY=1
    echo "[tb_tool_bt] using poetry runtime"
  else
    USE_POETRY=0
    echo "[tb_tool_bt] poetry not found, fallback to .venv + requirements.txt"
  fi
}

ensure_env_file() {
  if [ ! -f ".env" ]; then
    cat > .env <<EOF
DINGTALK_APPKEY=
DINGTALK_APPSECRET=

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
}

maybe_init_mysql() {
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
        echo "[tb_tool_bt] Try: INIT_MYSQL=1 MYSQL_ROOT_PASSWORD=your_root_password bash run_on_pc_daemon.sh start"
        exit 1
      fi
    else
      echo "[tb_tool_bt] ERROR: mysql client not found; cannot init MySQL automatically."
      exit 1
    fi
  fi
}

install_deps() {
  if [ "${USE_POETRY}" = "1" ]; then
    echo "[tb_tool_bt] Installing deps (poetry install --no-root)"
    poetry install --no-root
  else
    echo "[tb_tool_bt] Installing deps (.venv + pip install -r requirements.txt)"
    python3 -m venv .venv
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install -r requirements.txt
  fi
}

kill_port_process() {
  local port="$1"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"${port}" 2>/dev/null || true)"
  else
    pids="$(ss -ltnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true)"
  fi

  if [ -z "${pids}" ]; then
    echo "[tb_tool_bt] No process is using port ${port}."
    return 0
  fi

  echo "[tb_tool_bt] Found process on port ${port}: ${pids}"
  for pid in ${pids}; do
    if [ -n "${pid}" ] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "[tb_tool_bt] Killing pid ${pid} on port ${port}..."
      kill "${pid}" >/dev/null 2>&1 || true
      sleep 1
      if kill -0 "${pid}" >/dev/null 2>&1; then
        echo "[tb_tool_bt] Force killing pid ${pid}..."
        kill -9 "${pid}" >/dev/null 2>&1 || true
      fi
    fi
  done
}

start_daemon() {
  kill_port_process "${APP_PORT}"

  if is_running; then
    echo "[tb_tool_bt] ${DAEMON_NAME} already running (pid $(cat "${PID_FILE}"))."
    return 0
  fi

  echo "[tb_tool_bt] cwd: $(pwd)"
  ensure_prerequisites
  ensure_env_file
  install_deps
  maybe_init_mysql

  echo "[tb_tool_bt] Starting daemon on listen http://${APP_HOST}:${APP_PORT}"
  export FLASK_RUN_HOST="${APP_HOST}"
  export FLASK_RUN_PORT="${APP_PORT}"
  export AI_FLASK_BASE_URL="http://127.0.0.1:${APP_PORT}"
  export AI_TTYD_BASE_URL="http://${APP_PUBLIC_HOST}:{port}/"

  echo "[tb_tool_bt] Access URL: http://${APP_PUBLIC_HOST}:${APP_PORT}"
  if [ "${USE_POETRY}" = "1" ]; then
    nohup poetry run python app.py >> "${LOG_FILE}" 2>&1 &
  else
    nohup ./.venv/bin/python app.py >> "${LOG_FILE}" 2>&1 &
  fi
  echo $! > "${PID_FILE}"
  sleep 1

  if is_running; then
    echo "[tb_tool_bt] Started ${DAEMON_NAME} (pid $(cat "${PID_FILE}"))."
    echo "[tb_tool_bt] Log file: ${LOG_FILE}"
  else
    echo "[tb_tool_bt] ERROR: failed to start daemon, check log: ${LOG_FILE}"
    rm -f "${PID_FILE}"
    exit 1
  fi
}

stop_daemon() {
  if ! is_running; then
    echo "[tb_tool_bt] ${DAEMON_NAME} is not running."
    rm -f "${PID_FILE}" || true
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  echo "[tb_tool_bt] Stopping ${DAEMON_NAME} (pid ${pid})..."
  kill "${pid}" >/dev/null 2>&1 || true

  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if kill -0 "${pid}" >/dev/null 2>&1; then
    echo "[tb_tool_bt] Process did not exit gracefully, force killing..."
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi

  rm -f "${PID_FILE}"
  echo "[tb_tool_bt] Stopped."
}

show_status() {
  if is_running; then
    echo "[tb_tool_bt] ${DAEMON_NAME} is running (pid $(cat "${PID_FILE}"))."
    echo "[tb_tool_bt] Listen: http://${APP_HOST}:${APP_PORT}"
    echo "[tb_tool_bt] Access: http://${APP_PUBLIC_HOST}:${APP_PORT}"
    echo "[tb_tool_bt] Log: ${LOG_FILE}"
  else
    echo "[tb_tool_bt] ${DAEMON_NAME} is not running."
  fi
}

show_logs() {
  touch "${LOG_FILE}"
  tail -n 100 -f "${LOG_FILE}"
}

ACTION="${1:-start}"
case "${ACTION}" in
  start)
    start_daemon
    ;;
  stop)
    stop_daemon
    ;;
  restart)
    stop_daemon
    start_daemon
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  *)
    echo "Usage: bash run_on_pc_daemon.sh {start|stop|restart|status|logs}"
    exit 1
    ;;
esac

