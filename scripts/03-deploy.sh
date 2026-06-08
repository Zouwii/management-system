#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

echo "[deploy] latest package: ${LATEST_PACKAGE}"
echo "[deploy] target: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BASE_DIR}"

echo "[deploy] prepare remote directory and clean old project..."
# 强制使用 REMOTE_BASE_DIR；若当前用户无权限，尝试 sudo 提权创建并授权。
# 保留服务器已有的虚拟环境和环境配置，避免每次部署重装依赖/丢配置。
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "
  set -e
  if [ ! -d '${REMOTE_BASE_DIR}' ] || [ ! -w '${REMOTE_BASE_DIR}' ]; then
    echo '${REMOTE_PASS}' | sudo -S mkdir -p '${REMOTE_BASE_DIR}' || {
      echo '[deploy] 无法创建 ${REMOTE_BASE_DIR}，请确认 jz 具备 sudo 权限'
      exit 1
    }
    echo '${REMOTE_PASS}' | sudo -S chown -R '${REMOTE_USER}:${REMOTE_USER}' '${REMOTE_BASE_DIR}' || {
      echo '[deploy] 无法修改 ${REMOTE_BASE_DIR} 权限，请联系管理员授权'
      exit 1
    }
  fi
  cd '${REMOTE_BASE_DIR}'
  rm -rf .tb_tool_bt_preserve
  mkdir -p .tb_tool_bt_preserve
  if [ -d tb_tool_bt/backend/.venv ]; then
    mv tb_tool_bt/backend/.venv .tb_tool_bt_preserve/.venv
  fi
  if [ -f tb_tool_bt/backend/.env ]; then
    mv tb_tool_bt/backend/.env .tb_tool_bt_preserve/.env
  fi
  rm -rf tb_tool_bt
"

echo "[deploy] upload package..."
sshpass -p "${REMOTE_PASS}" scp -o StrictHostKeyChecking=no "${LATEST_PACKAGE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BASE_DIR}/"

echo "[deploy] local cleanup: rm ${LATEST_PACKAGE}"
rm -f "${LATEST_PACKAGE}"

echo "[deploy] extract and start daemon..."
sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
  "bash -lc 'set -e; export PATH=\"\$HOME/.local/bin:\$PATH\"; cd \"${REMOTE_BASE_DIR}\"; tar -vzxf \"${PACKAGE_NAME}\"; rm -f \"${PACKAGE_NAME}\"; if [ -d .tb_tool_bt_preserve/.venv ]; then mv .tb_tool_bt_preserve/.venv \"${REMOTE_PROJECT_DIR}/backend/.venv\"; fi; if [ -f .tb_tool_bt_preserve/.env ]; then mv .tb_tool_bt_preserve/.env \"${REMOTE_PROJECT_DIR}/backend/.env\"; fi; rm -rf .tb_tool_bt_preserve; cd \"${REMOTE_PROJECT_DIR}/backend\"; echo \"[deploy] remote PATH: \$PATH\"; if [[ -x \"./run_on_pc_daemon\" ]]; then ./run_on_pc_daemon start; elif [[ -x \"./run_on_pc_daemon.sh\" ]]; then bash ./run_on_pc_daemon.sh start; else echo \"run_on_pc_daemon(.sh) 不存在或不可执行\"; exit 1; fi'"

echo "[deploy] done."
