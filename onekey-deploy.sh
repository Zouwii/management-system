#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[05-onekey] step 1/2: package"
bash "${SCRIPT_DIR}/scripts/02-package.sh"

echo "[05-onekey] step 2/2: deploy"
bash "${SCRIPT_DIR}/scripts/03-deploy.sh"

echo "[05-onekey] step 3/5: sync diagkit skills to server"
bash "${SCRIPT_DIR}/scripts/sync-diagkit-skills.sh"

echo "[05-onekey] step 4/5: deploy diagkit scripts to server"
bash "${SCRIPT_DIR}/scripts/deploy-diagkit-scripts.sh"

echo "[05-onekey] step 5/5: restart diagkit ttyd on port 5433"
bash "${SCRIPT_DIR}/scripts/manage-diagkit-ttyd.sh" restart
# 不想用 diagkit 了就注释掉上一行 ↑

echo "[05-onekey] done."
