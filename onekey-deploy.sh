#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[05-onekey] step 1/2: package"
bash "${SCRIPT_DIR}/scripts/02-package.sh"

echo "[05-onekey] step 2/2: deploy"
bash "${SCRIPT_DIR}/scripts/03-deploy.sh"

echo "[05-onekey] done."
