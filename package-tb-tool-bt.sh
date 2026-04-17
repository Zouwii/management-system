#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="tb_tool_bt"
TS="$(date +%Y%m%d-%H%M%S)"
TAR_DIR="${SCRIPT_DIR}/tar"
OUT_TS="${TAR_DIR}/${PROJECT_NAME}_backend-${TS}.tar.gz"
STAGE_DIR="${SCRIPT_DIR}/.package_stage/${PROJECT_NAME}"

FRONTEND_API_MODE="${FRONTEND_API_MODE:-real}"
echo "[${PROJECT_NAME}] building frontend (npm run build, VITE_API_MODE=${FRONTEND_API_MODE})..."
pushd "${SCRIPT_DIR}/frontend-react" >/dev/null
if [ -f "package-lock.json" ]; then
  npm ci
else
  npm install
fi
VITE_API_MODE="${FRONTEND_API_MODE}" npm run build
popd >/dev/null

echo "[${PROJECT_NAME}] preparing package stage..."
rm -rf "${SCRIPT_DIR}/.package_stage"
mkdir -p "${TAR_DIR}"
mkdir -p "${STAGE_DIR}"

# 只打包 backend 部署所需目录，避免把开发缓存和大体积依赖带进去
cp -r "${SCRIPT_DIR}/backend" "${STAGE_DIR}/backend"

echo "[${PROJECT_NAME}] cleaning unnecessary files..."
rm -rf \
  "${STAGE_DIR}/backend/.venv" \
  "${STAGE_DIR}/backend/__pycache__" \
  "${STAGE_DIR}/backend/.pytest_cache" \
  "${STAGE_DIR}/backend/data"

find "${STAGE_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} + || true
find "${STAGE_DIR}" -type d -name ".mypy_cache" -prune -exec rm -rf {} + || true
find "${STAGE_DIR}" -type d -name ".ruff_cache" -prune -exec rm -rf {} + || true
find "${STAGE_DIR}" -type d -name ".git" -prune -exec rm -rf {} + || true
find "${STAGE_DIR}" -type f -name "*.pyc" -delete || true

echo "[${PROJECT_NAME}] creating tar.gz..."
tar -czf "${OUT_TS}" -C "${SCRIPT_DIR}/.package_stage" "${PROJECT_NAME}"

echo "[${PROJECT_NAME}] done."
echo "  versioned: ${OUT_TS}"

rm -rf "${SCRIPT_DIR}/.package_stage"
