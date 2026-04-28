#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[onekey] step 1/2: package"
bash "${SCRIPT_DIR}/package-tb-tool-bt.sh"

echo "[onekey] step 2/2: deploy"
bash "${SCRIPT_DIR}/deploy-tb-tool-bt.sh"

echo "[onekey] done."
