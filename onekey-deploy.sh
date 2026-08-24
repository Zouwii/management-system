#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[05-onekey] step 1/3: package"
bash "${SCRIPT_DIR}/scripts/02-package.sh"

echo "[05-onekey] step 2/3: deploy management-system"
bash "${SCRIPT_DIR}/scripts/03-deploy.sh"

if [[ "${DEPLOY_DIAGKIT_6433:-true}" == "true" ]]; then
  echo "[05-onekey] step 3/3: deploy and restart DiagKit 6433"
  bash "${SCRIPT_DIR}/scripts/manage-diagkit-6433.sh" deploy
else
  echo "[05-onekey] step 3/3: skip DiagKit 6433 (DEPLOY_DIAGKIT_6433=false)"
fi

echo "[05-onekey] done."
