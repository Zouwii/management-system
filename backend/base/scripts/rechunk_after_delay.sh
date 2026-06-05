#!/usr/bin/env bash
set -euo pipefail

APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:5002}"
DELAY_SECONDS="${1:-${DELAY_SECONDS:-10800}}"
LOG_FILE="${LOG_FILE:-$(pwd)/runtime/rechunk_after_delay.log}"

mkdir -p "$(dirname "${LOG_FILE}")"

{
  echo "[$(date '+%F %T')] scheduled rechunk after ${DELAY_SECONDS}s"
  sleep "${DELAY_SECONDS}"
  echo "[$(date '+%F %T')] starting rechunk"
  curl -sS -X POST "${APP_BASE_URL}/api/bt/ai/knowledge/rechunk" \
    -H "Content-Type: application/json" \
    -d '{"all":true}'
  echo
  echo "[$(date '+%F %T')] rechunk request finished"
} >> "${LOG_FILE}" 2>&1
