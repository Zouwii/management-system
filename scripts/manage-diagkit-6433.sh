#!/usr/bin/env bash
# Deploy and remotely manage the modular DiagKit instance on port 6433.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIAGNOSIS_AGENT_ROOT="${DIAGNOSIS_AGENT_ROOT:-${WORKSPACE_ROOT}/diagnosis-agent}"
JZ_SKILLS_ROOT="${JZ_SKILLS_ROOT:-${WORKSPACE_ROOT}/jz-claude-skills}"
REMOTE_USER="${DIAGKIT_REMOTE_USER:-jz}"
REMOTE_HOST="${DIAGKIT_REMOTE_HOST:-172.19.3.79}"
REMOTE_PASS="${DIAGKIT_REMOTE_PASS:-}"
REMOTE_ROOT="${DIAGKIT_REMOTE_ROOT:-/home/jz/diagkit}"
REMOTE_SCRIPTS="${REMOTE_ROOT}/scripts"
REMOTE_DOCS="${REMOTE_ROOT}/diagnosis-source-docs"
REMOTE_SKILLS="${REMOTE_ROOT}/jz-claude-skills-modular"
REMOTE_SERVICE="${REMOTE_SCRIPTS}/diagkit-6433-service.sh"
SSH=(ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}")
SCP=(scp -o StrictHostKeyChecking=no)
if [[ -n "${REMOTE_PASS}" ]]; then
  SSH=(sshpass -p "${REMOTE_PASS}" "${SSH[@]}")
  SCP=(sshpass -p "${REMOTE_PASS}" "${SCP[@]}")
fi

require_tools() {
  command -v ssh >/dev/null 2>&1 || { echo "[diagkit-6433] missing ssh" >&2; exit 1; }
  command -v scp >/dev/null 2>&1 || { echo "[diagkit-6433] missing scp" >&2; exit 1; }
  if [[ -n "${REMOTE_PASS}" ]]; then
    command -v sshpass >/dev/null 2>&1 || { echo "[diagkit-6433] DIAGKIT_REMOTE_PASS requires sshpass" >&2; exit 1; }
  fi
  command -v tar >/dev/null 2>&1 || { echo "[diagkit-6433] missing tar" >&2; exit 1; }
}

validate_sources() {
  [[ -f "${SCRIPT_DIR}/diagkit-launch-modular.sh" ]] || { echo "[diagkit-6433] missing modular launcher" >&2; exit 1; }
  [[ -d "${DIAGNOSIS_AGENT_ROOT}/source-docs/jstate_error_codes/agent" ]] || { echo "[diagkit-6433] missing JState agent documents" >&2; exit 1; }
  [[ -f "${DIAGNOSIS_AGENT_ROOT}/source-docs/onsite-top/high-frequency-problem-map.json" ]] || { echo "[diagkit-6433] missing high-frequency map" >&2; exit 1; }
}

validate_skills() {
  [[ -f "${JZ_SKILLS_ROOT}/skills/diagnosis-orchestrator/SKILL.md" ]] || { echo "[diagkit-6433] missing diagnosis-orchestrator" >&2; exit 1; }
  [[ -x "${JZ_SKILLS_ROOT}/scripts/diagnosis" ]] || { echo "[diagkit-6433] missing executable diagnosis CLI" >&2; exit 1; }
}

deploy_scripts() {
  echo "[diagkit-6433] deploying service and launcher"
  "${SSH[@]}" "mkdir -p '${REMOTE_SCRIPTS}' '${REMOTE_ROOT}/logs-modular' '${REMOTE_ROOT}/.pending_users-modular'; test -f '${REMOTE_SCRIPTS}/diagkit-auth-proxy-modular.py'"
  "${SCP[@]}" \
    "${SCRIPT_DIR}/diagkit-6433-service.sh" \
    "${SCRIPT_DIR}/diagkit-launch-modular.sh" \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SCRIPTS}/"
  "${SSH[@]}" "chmod +x '${REMOTE_SERVICE}' '${REMOTE_SCRIPTS}/diagkit-launch-modular.sh'"
}

sync_skills() {
  local stage backup
  validate_skills
  stage="$("${SSH[@]}" "mktemp -d '${REMOTE_ROOT}/.skills-stage-XXXXXXXX'")"
  backup="$("${SSH[@]}" "mktemp -d '${REMOTE_ROOT}/deploy-backups/skills-XXXXXXXX'")"
  echo "[diagkit-6433] staging skills in ${stage}"
  tar -C "${JZ_SKILLS_ROOT}" --exclude='__pycache__' --exclude='*.pyc' -cf - skills scripts \
    | "${SSH[@]}" "tar -C '${stage}' -xf -"
  "${SSH[@]}" "set -e; \
    mkdir -p '${REMOTE_SKILLS}'; \
    if test -d '${REMOTE_SKILLS}/skills'; then mv '${REMOTE_SKILLS}/skills' '${backup}/skills'; fi; \
    if test -d '${REMOTE_SKILLS}/scripts'; then mv '${REMOTE_SKILLS}/scripts' '${backup}/scripts'; fi; \
    mv '${stage}/skills' '${REMOTE_SKILLS}/skills'; \
    mv '${stage}/scripts' '${REMOTE_SKILLS}/scripts'; \
    rmdir '${stage}'; \
    test -f '${REMOTE_SKILLS}/skills/diagnosis-orchestrator/SKILL.md'; \
    test -x '${REMOTE_SKILLS}/scripts/diagnosis'; \
    echo '[diagkit-6433] skill backup: ${backup}'"
}

sync_documents() {
  local stage backup
  validate_sources
  stage="$("${SSH[@]}" "mktemp -d '${REMOTE_ROOT}/.source-docs-stage-XXXXXXXX'")"
  backup="$("${SSH[@]}" "mktemp -d '${REMOTE_ROOT}/deploy-backups/source-docs-XXXXXXXX'")"
  echo "[diagkit-6433] staging documents in ${stage}"
  "${SSH[@]}" "mkdir -p '${stage}/jstate_error_codes' '${stage}/onsite-top'"

  tar -C "${DIAGNOSIS_AGENT_ROOT}/source-docs/jstate_error_codes" -cf - agent \
    | "${SSH[@]}" "tar -C '${stage}/jstate_error_codes' -xf -"
  tar -C "${DIAGNOSIS_AGENT_ROOT}/source-docs/onsite-top" \
    --exclude='./scripts' --exclude='./__pycache__' -cf - . \
    | "${SSH[@]}" "tar -C '${stage}/onsite-top' -xf -"

  "${SSH[@]}" "set -e; \
    mkdir -p '${REMOTE_DOCS}/jstate_error_codes'; \
    if test -d '${REMOTE_DOCS}/jstate_error_codes/agent'; then mv '${REMOTE_DOCS}/jstate_error_codes/agent' '${backup}/jstate-agent'; fi; \
    if test -d '${REMOTE_DOCS}/onsite-top'; then mv '${REMOTE_DOCS}/onsite-top' '${backup}/onsite-top'; fi; \
    mv '${stage}/jstate_error_codes/agent' '${REMOTE_DOCS}/jstate_error_codes/agent'; \
    mv '${stage}/onsite-top' '${REMOTE_DOCS}/onsite-top'; \
    rmdir '${stage}/jstate_error_codes' '${stage}'; \
    test -n \"\$(find '${REMOTE_DOCS}/jstate_error_codes/agent' -maxdepth 1 -type f -name '*.md' -print -quit)\"; \
    test -f '${REMOTE_DOCS}/onsite-top/high-frequency-problem-map.json'; \
    echo '[diagkit-6433] document backup: ${backup}'"
}

remote_action() {
  "${SSH[@]}" "bash '${REMOTE_SERVICE}' '$1'"
}

check_prerequisites() {
  validate_sources
  validate_skills
  "${SSH[@]}" "set -e; command -v ttyd >/dev/null; command -v python3 >/dev/null; command -v tar >/dev/null; test -f '${REMOTE_SCRIPTS}/diagkit-auth-proxy-modular.py'; mkdir -p '${REMOTE_ROOT}/deploy-backups'; echo '[diagkit-6433] prerequisites ready'"
}

require_tools
case "${1:-status}" in
  deploy)
    check_prerequisites
    deploy_scripts
    sync_skills
    sync_documents
    remote_action restart
    ;;
  sync-skills) sync_skills ;;
  sync-docs) sync_documents ;;
  check) check_prerequisites ;;
  start|stop|restart|status) remote_action "$1" ;;
  *) echo "usage: $0 {check|deploy|sync-skills|sync-docs|start|stop|restart|status}" >&2; exit 2 ;;
esac
