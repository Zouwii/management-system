#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAR_DIR="${SCRIPT_DIR}/tar"
PACKAGE_GLOB="${TAR_DIR}/tb_tool_bt_backend-*.tar.gz"

REMOTE_USER="jz"
REMOTE_HOST="172.19.3.79"
REMOTE_PASS="1"
REMOTE_BASE_DIR="/home/jz/zhr"
REMOTE_PROJECT_DIR="${REMOTE_BASE_DIR}/tb_tool_bt"

if ! command -v sshpass >/dev/null 2>&1; then
  echo "缺少 sshpass，请先安装（例如: sudo apt-get install -y sshpass）"
  exit 1
fi

LATEST_PACKAGE="$(ls -1t ${PACKAGE_GLOB} 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST_PACKAGE}" ]]; then
  echo "未找到可部署包: ${PACKAGE_GLOB}"
  exit 1
fi

PACKAGE_NAME="$(basename "${LATEST_PACKAGE}")"
DEPLOY_STAMP="$(date +%Y%m%d-%H%M%S)"
PRESERVE_DIR=".tb_tool_bt_preserve-${DEPLOY_STAMP}"

echo "[deploy] latest package: ${LATEST_PACKAGE}"
echo "[deploy] target: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BASE_DIR}"
echo "[deploy] upload package before stopping the running service..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no \
  "${LATEST_PACKAGE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BASE_DIR}/"

echo "[deploy] stop daemon and preserve persistent data..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no \
  "${REMOTE_USER}@${REMOTE_HOST}" bash -s -- "${REMOTE_BASE_DIR}" "${PRESERVE_DIR}" <<'REMOTE_PREP'
set -euo pipefail
base_dir="$1"
preserve_dir="$2"
cd "$base_dir"
if [ -x tb_tool_bt/backend/run_on_pc_daemon ]; then
  tb_tool_bt/backend/run_on_pc_daemon stop
elif [ -x tb_tool_bt/backend/run_on_pc_daemon.sh ]; then
  bash tb_tool_bt/backend/run_on_pc_daemon.sh stop
fi
mkdir -p "$preserve_dir"
if [ -d tb_tool_bt/backend/.venv ]; then mv tb_tool_bt/backend/.venv "$preserve_dir/.venv"; fi
if [ -f tb_tool_bt/backend/.env ]; then mv tb_tool_bt/backend/.env "$preserve_dir/.env"; fi
if [ -d tb_tool_bt/backend/data ]; then mv tb_tool_bt/backend/data "$preserve_dir/data"; fi
if [ -d tb_tool_bt/backend/local_models ]; then mv tb_tool_bt/backend/local_models "$preserve_dir/local_models"; fi
if [ -d tb_tool_bt/backend/runtime ]; then
  mv tb_tool_bt/backend/runtime "$preserve_dir/runtime"
  rm -f "$preserve_dir/runtime/tb_tool_bt_daemon.pid"
fi
rm -rf tb_tool_bt
REMOTE_PREP

echo "[deploy] extract, restore persistent data and start daemon..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no \
  "${REMOTE_USER}@${REMOTE_HOST}" bash -s -- "${REMOTE_BASE_DIR}" "${REMOTE_PROJECT_DIR}" "${PACKAGE_NAME}" "${PRESERVE_DIR}" <<'REMOTE_INSTALL'
set -euo pipefail
base_dir="$1"
project_dir="$2"
package_name="$3"
preserve_dir="$4"
cd "$base_dir"
tar -zxf "$package_name"
backend_dir="$project_dir/backend"
if [ -d "$preserve_dir/.venv" ]; then mv "$preserve_dir/.venv" "$backend_dir/.venv"; fi
if [ -f "$preserve_dir/.env" ]; then mv "$preserve_dir/.env" "$backend_dir/.env"; fi
if [ -d "$preserve_dir/data" ]; then rm -rf "$backend_dir/data"; mv "$preserve_dir/data" "$backend_dir/data"; fi
if [ -d "$preserve_dir/local_models" ]; then rm -rf "$backend_dir/local_models"; mv "$preserve_dir/local_models" "$backend_dir/local_models"; fi
if [ -d "$preserve_dir/runtime" ]; then
  if [ -d "$backend_dir/runtime/shared" ]; then mv "$backend_dir/runtime/shared" "$preserve_dir/packaged_shared"; fi
  rm -rf "$backend_dir/runtime"
  mv "$preserve_dir/runtime" "$backend_dir/runtime"
  if [ -d "$preserve_dir/packaged_shared" ]; then
    rm -rf "$backend_dir/runtime/shared"
    mv "$preserve_dir/packaged_shared" "$backend_dir/runtime/shared"
  fi
fi
rm -rf "$preserve_dir"
cd "$backend_dir"
mkdir -p runtime
sed -i '/^RERANK_ENABLED=/d' .env
echo 'RERANK_ENABLED=true' >> .env
echo "[deploy] rerank enabled"
if [ -x ./run_on_pc_daemon ]; then
  RERANK_ENABLED=true ./run_on_pc_daemon start
elif [ -x ./run_on_pc_daemon.sh ]; then
  RERANK_ENABLED=true bash ./run_on_pc_daemon.sh start
else
  echo "run_on_pc_daemon(.sh) 不存在或不可执行" >&2
  exit 1
fi
health_ok=false
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:5002/api/bt/health >/dev/null; then
    health_ok=true
    break
  fi
  sleep 1
done
if [[ "$health_ok" != "true" ]]; then
  echo "[deploy] health check failed" >&2
  tail -80 runtime/tb_tool_bt_daemon.log || true
  exit 1
fi
echo "[deploy] health check passed"
REMOTE_INSTALL

echo "[deploy] local cleanup: rm ${LATEST_PACKAGE}"
rm -f "${LATEST_PACKAGE}"
echo "[deploy] done."
