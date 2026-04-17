#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG_NAME="${1:-}"
TAG_MESSAGE="${2:-}"

if [[ -z "${TAG_NAME}" ]]; then
  echo "用法: ./tag-and-package.sh <tag> [message]"
  echo "示例: ./tag-and-package.sh v1.2.1 \"release v1.2.1\""
  exit 1
fi

if git rev-parse -q --verify "refs/tags/${TAG_NAME}" >/dev/null; then
  echo "tag 已存在: ${TAG_NAME}"
  exit 1
fi

if [[ -n "${TAG_MESSAGE}" ]]; then
  git tag -a "${TAG_NAME}" -m "${TAG_MESSAGE}"
else
  git tag "${TAG_NAME}"
fi

echo "[tag-and-package] 已创建 tag: ${TAG_NAME}"
echo "[tag-and-package] 开始执行打包脚本..."
bash "${SCRIPT_DIR}/package-tb-tool-bt.sh"
echo "[tag-and-package] 打包完成。产物位于: ${SCRIPT_DIR}/tar/"
