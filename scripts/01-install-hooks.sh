#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HOOK="${SCRIPT_DIR}/.githooks/pre-push"
TARGET_HOOK="${SCRIPT_DIR}/.git/hooks/pre-push"

if [[ ! -f "${REPO_HOOK}" ]]; then
  echo "missing repo hook: ${REPO_HOOK}"
  exit 1
fi

mkdir -p "${SCRIPT_DIR}/.git/hooks"
cp "${REPO_HOOK}" "${TARGET_HOOK}"
chmod +x "${TARGET_HOOK}"
chmod +x "${SCRIPT_DIR}/02-package.sh" || true

echo "installed local hook: ${TARGET_HOOK}"
echo "now IDE tag + push will run pre-push checks."
echo "CI will package on tag by default; set LOCAL_TAG_PACKAGE=1 to enable local package before push."
