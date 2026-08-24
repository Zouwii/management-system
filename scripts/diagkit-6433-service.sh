#!/usr/bin/env bash
# Manage the modular DiagKit terminal exposed on 6433.
set -euo pipefail

DIAGKIT_ROOT="${DIAGKIT_ROOT:-/home/jz/diagkit}"
SCRIPTS_DIR="${DIAGKIT_ROOT}/scripts"
LAUNCH_SCRIPT="${SCRIPTS_DIR}/diagkit-launch-modular.sh"
PROXY_SCRIPT="${SCRIPTS_DIR}/diagkit-auth-proxy-modular.py"
LOG_DIR="${DIAGKIT_ROOT}/logs-modular"
PENDING_DIR="${DIAGKIT_ROOT}/.pending_users-modular"
TTYD_PORT="${DIAGKIT_TTYD_PORT_INTERNAL:-6434}"
PROXY_PORT="${DIAGKIT_PROXY_PORT:-6433}"
TTYD_PID_FILE="${LOG_DIR}/ttyd.pid"
PROXY_PID_FILE="${LOG_DIR}/proxy.pid"
TTYD_LOG="${LOG_DIR}/ttyd.log"
PROXY_LOG="${LOG_DIR}/proxy.log"

mkdir -p "${LOG_DIR}" "${PENDING_DIR}"

ttyd_bin() {
  if command -v ttyd >/dev/null 2>&1; then
    command -v ttyd
  elif [[ -x /usr/local/bin/ttyd ]]; then
    echo /usr/local/bin/ttyd
  fi
}

pid_running() {
  local pid_file="$1" expected="$2" pid command_line
  [[ -f "${pid_file}" ]] || return 1
  pid="$(tr -dc '0-9' < "${pid_file}")"
  [[ -n "${pid}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  command_line="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  [[ "${command_line}" == *"${expected}"* ]]
}

wait_for_process() {
  local pid="$1"
  for _ in {1..20}; do
    kill -0 "${pid}" 2>/dev/null || return 1
    sleep 0.25
  done
}

start_ttyd() {
  local binary pid
  if pid_running "${TTYD_PID_FILE}" "${LAUNCH_SCRIPT}"; then
    echo "[diagkit-6433] ttyd already running (PID $(cat "${TTYD_PID_FILE}"), port ${TTYD_PORT})"
    return
  fi
  rm -f "${TTYD_PID_FILE}"
  binary="$(ttyd_bin)"
  [[ -n "${binary}" ]] || { echo "[diagkit-6433] ttyd is not installed" >&2; return 1; }
  [[ -f "${LAUNCH_SCRIPT}" ]] || { echo "[diagkit-6433] missing ${LAUNCH_SCRIPT}" >&2; return 1; }

  nohup "${binary}" -W -i 127.0.0.1 -p "${TTYD_PORT}" \
    bash "${LAUNCH_SCRIPT}" >> "${TTYD_LOG}" 2>&1 &
  pid=$!
  echo "${pid}" > "${TTYD_PID_FILE}"
  wait_for_process "${pid}" || {
    echo "[diagkit-6433] ttyd failed; inspect ${TTYD_LOG}" >&2
    rm -f "${TTYD_PID_FILE}"
    return 1
  }
  echo "[diagkit-6433] ttyd started (PID ${pid}, port ${TTYD_PORT})"
}

start_proxy() {
  local pid
  if pid_running "${PROXY_PID_FILE}" "${PROXY_SCRIPT}"; then
    echo "[diagkit-6433] auth proxy already running (PID $(cat "${PROXY_PID_FILE}"), port ${PROXY_PORT})"
    return
  fi
  rm -f "${PROXY_PID_FILE}"
  [[ -f "${PROXY_SCRIPT}" ]] || { echo "[diagkit-6433] missing ${PROXY_SCRIPT}" >&2; return 1; }

  nohup env \
    DIAGKIT_PROXY_PORT="${PROXY_PORT}" \
    DIAGKIT_TTYD_PORT_INTERNAL="${TTYD_PORT}" \
    DIAGKIT_LOG_DIR="${LOG_DIR}" \
    DIAGKIT_PENDING_DIR="${PENDING_DIR}" \
    python3 "${PROXY_SCRIPT}" --port="${PROXY_PORT}" --ttyd-port="${TTYD_PORT}" \
    >> "${PROXY_LOG}" 2>&1 &
  pid=$!
  echo "${pid}" > "${PROXY_PID_FILE}"
  wait_for_process "${pid}" || {
    echo "[diagkit-6433] auth proxy failed; inspect ${PROXY_LOG}" >&2
    rm -f "${PROXY_PID_FILE}"
    return 1
  }
  echo "[diagkit-6433] auth proxy started (PID ${pid}, port ${PROXY_PORT})"
}

stop_process() {
  local name="$1" pid_file="$2" expected="$3" pid
  if ! pid_running "${pid_file}" "${expected}"; then
    echo "[diagkit-6433] ${name} not running"
    rm -f "${pid_file}"
    return
  fi
  pid="$(cat "${pid_file}")"
  kill "${pid}" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
  rm -f "${pid_file}"
  echo "[diagkit-6433] ${name} stopped"
}

status_process() {
  local name="$1" pid_file="$2" expected="$3" port="$4"
  if pid_running "${pid_file}" "${expected}"; then
    echo "[diagkit-6433] ${name} running (PID $(cat "${pid_file}"), port ${port})"
    return 0
  fi
  echo "[diagkit-6433] ${name} not running"
  return 1
}

do_start() {
  start_ttyd
  start_proxy
  curl -fsS --max-time 5 "http://127.0.0.1:${PROXY_PORT}/" >/dev/null
  echo "[diagkit-6433] ready: http://$(hostname -I | awk '{print $1}'):${PROXY_PORT}"
}

do_stop() {
  stop_process auth-proxy "${PROXY_PID_FILE}" "${PROXY_SCRIPT}"
  stop_process ttyd "${TTYD_PID_FILE}" "${LAUNCH_SCRIPT}"
}

do_status() {
  local failed=0
  status_process auth-proxy "${PROXY_PID_FILE}" "${PROXY_SCRIPT}" "${PROXY_PORT}" || failed=1
  status_process ttyd "${TTYD_PID_FILE}" "${LAUNCH_SCRIPT}" "${TTYD_PORT}" || failed=1
  if curl -fsS --max-time 5 "http://127.0.0.1:${PROXY_PORT}/" >/dev/null; then
    echo "[diagkit-6433] HTTP ${PROXY_PORT} healthy"
  else
    echo "[diagkit-6433] HTTP ${PROXY_PORT} unavailable"
    failed=1
  fi
  return "${failed}"
}

case "${1:-status}" in
  start) do_start ;;
  stop) do_stop ;;
  restart) do_stop; do_start ;;
  status) do_status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
