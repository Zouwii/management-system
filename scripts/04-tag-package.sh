#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG_NAME="${1:-}"
TAG_MESSAGE="${2:-}"
PUSH_REMOTE="${3:-}"

if [[ -z "${TAG_NAME}" ]]; then
  echo "用法: ./04-tag-package.sh <tag> [message] [--push]"
  echo "示例:"
  echo "  仅本地打 tag + 本地打包: ./04-tag-package.sh v1.2.1 \"release v1.2.1\""
  echo "  本地打 tag + 本地打包 + push 远端: ./04-tag-package.sh v1.2.1 \"release v1.2.1\" --push"
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

echo "[04-tag-package] 已创建 tag: ${TAG_NAME}"
echo "[04-tag-package] 开始执行打包脚本..."
bash "${SCRIPT_DIR}/02-package.sh"
echo "[04-tag-package] 打包完成。产物位于: ${SCRIPT_DIR}/tar/"

if [[ "${PUSH_REMOTE}" == "--push" ]]; then
  echo "[04-tag-package] 推送 tag 到远端..."
  git push origin "${TAG_NAME}"
  echo "[04-tag-package] 远端推送完成: ${TAG_NAME}"
fi
