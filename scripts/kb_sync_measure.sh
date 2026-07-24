#!/usr/bin/env bash
# ============================================================
# KB API 用量测试 — 逐知识库 sync 并记录钉钉 API 调用量
# 用法: bash scripts/kb_sync_measure.sh
# ============================================================
set -euo pipefail

API_BASE="http://127.0.0.1:5002/api/bt"
LOG_DIR="/home/jz/zhr/tb_tool_bt/backend/runtime"
RESULT_FILE="${LOG_DIR}/kb_api_usage_$(date +%Y%m%d_%H%M%S).log"
SUMMARY_FILE="${LOG_DIR}/kb_api_usage_summary.txt"

WORKSPACES=(
  "本体开发部|1oam4Sk7BMLXxn8K"
  "研发共享文档|By8jQSbJyWLAL30M"
  "研发体系文档【JZ-TOTAL】|yq8ZkS3KYJW4enaX"
  "研发体系全员文档库|9Bv51SJGoKxPBjv3"
  "研发共享文档（非公开）|X1v4RS7ybR4GeZ8P"
  "产品专项知识库（2023上半年-2025年）|5zaVASrJnl5bDo8y"
  "研发专项知识库（2023上半年-2026年）|9Bv51SWzXGOJOzv3"
  "订单专项知识库（2022-2025）|bJvOOSLN3yLzGgvK"
  "产品信息门户|OQ0xySKEGYKEG48B"
  "订单项目信息门户|MJ0pDSwlOEkMqQ0E"
)

echo "==============================================" | tee "$RESULT_FILE"
echo "  KB 知识库 API 用量测试"                       | tee -a "$RESULT_FILE"
echo "  开始时间: $(date '+%Y-%m-%d %H:%M:%S')"        | tee -a "$RESULT_FILE"
echo "  共 ${#WORKSPACES[@]} 个知识库"                  | tee -a "$RESULT_FILE"
echo "==============================================" | tee -a "$RESULT_FILE"

# ── 清空 api_call_logs ──
mysql -u root -p123456 benti_management -e "DELETE FROM api_call_logs;" 2>/dev/null
echo "[$(date '+%H:%M:%S')] api_call_logs 已清空" | tee -a "$RESULT_FILE"
echo "" | tee -a "$RESULT_FILE"

TOTAL_SYNC_NODES=0
TOTAL_SYNC_DOCS=0
TOTAL_FAIL_NODES=0
TOTAL_FAIL_DOCS=0
OVERALL_START=$(date +%s)

for i in "${!WORKSPACES[@]}"; do
  IFS='|' read -r WS_NAME WS_ID <<< "${WORKSPACES[$i]}"
  IDX=$((i + 1))
  TOTAL=${#WORKSPACES[@]}

  echo "── [$IDX/$TOTAL] ${WS_NAME} ──────────────────────────────" | tee -a "$RESULT_FILE"
  echo "   开始: $(date '+%H:%M:%S') | workspace_id: ${WS_ID}" | tee -a "$RESULT_FILE"

  WS_START=$(date +%s)
  RESP=$(curl -s -X POST "${API_BASE}/ai/knowledge/sync" \
    -H 'Content-Type: application/json' \
    -d "{\"workspace_id\":\"${WS_ID}\"}" --max-time 7200 2>&1) || true
  WS_END=$(date +%s)
  WS_DUR=$((WS_END - WS_START))

  # 解析结果
  SYNC_NODES=0; SYNC_DOCS=0; FAIL_NODES=0; FAIL_DOCS=0; SYNC_DUR=0
  echo "$RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('code')==200:
    dd=d['data']
    print(f'{dd.get(\"syncedNodes\",0)}|{dd.get(\"syncedDocs\",0)}|{dd.get(\"failedNodes\",0)}|{dd.get(\"failedDocs\",0)}|{dd.get(\"durationSec\",0)}')
else:
    print('0|0|0|0|0')
" 2>/dev/null > /tmp/_sync_parsed.txt || echo "0|0|0|0|0" > /tmp/_sync_parsed.txt
  IFS='|' read -r SYNC_NODES SYNC_DOCS FAIL_NODES FAIL_DOCS SYNC_DUR < /tmp/_sync_parsed.txt

  # API 用量
  API_TOTAL=$(mysql -u root -p123456 benti_management -N -e "SELECT COUNT(*) FROM api_call_logs;" 2>/dev/null)
  API_BY_EP=$(mysql -u root -p123456 benti_management -N -e \
    "SELECT endpoint, COUNT(*) FROM api_call_logs GROUP BY endpoint ORDER BY COUNT(*) DESC;" 2>/dev/null)

  echo "   结束: $(date '+%H:%M:%S') | 耗时: ${WS_DUR}s" | tee -a "$RESULT_FILE"
  echo "   syncNodes=${SYNC_NODES}  syncDocs=${SYNC_DOCS}  failNodes=${FAIL_NODES}  failDocs=${FAIL_DOCS}" | tee -a "$RESULT_FILE"
  echo "   API累计: ${API_TOTAL}" | tee -a "$RESULT_FILE"
  echo "$API_BY_EP" | while read -r ep cnt; do
    [ -z "$ep" ] && continue
    echo "     ${ep}: ${cnt}" | tee -a "$RESULT_FILE"
  done
  echo "" | tee -a "$RESULT_FILE"

  TOTAL_SYNC_NODES=$((TOTAL_SYNC_NODES + SYNC_NODES))
  TOTAL_SYNC_DOCS=$((TOTAL_SYNC_DOCS + SYNC_DOCS))
  TOTAL_FAIL_NODES=$((TOTAL_FAIL_NODES + FAIL_NODES))
  TOTAL_FAIL_DOCS=$((TOTAL_FAIL_DOCS + FAIL_DOCS))
done

OVERALL_END=$(date +%s)
OVERALL_DUR=$((OVERALL_END - OVERALL_START))

FINAL_API=$(mysql -u root -p123456 benti_management -N -e "SELECT COUNT(*) FROM api_call_logs;" 2>/dev/null)
FINAL_BY_EP=$(mysql -u root -p123456 benti_management -N -e \
  "SELECT endpoint, COUNT(*) FROM api_call_logs GROUP BY endpoint ORDER BY COUNT(*) DESC;" 2>/dev/null)

{
  echo ""
  echo "=============================================="
  echo "  最终汇总"
  echo "=============================================="
  echo "  结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "  总耗时:   ${OVERALL_DUR}s ($((OVERALL_DUR / 60))m $((OVERALL_DUR % 60))s)"
  echo "  知识库数: ${#WORKSPACES[@]}"
  echo "  syncedNodes:  ${TOTAL_SYNC_NODES}"
  echo "  syncedDocs:   ${TOTAL_SYNC_DOCS}"
  echo "  failedNodes:  ${TOTAL_FAIL_NODES}"
  echo "  failedDocs:   ${TOTAL_FAIL_DOCS}"
  echo "  API总调用量:  ${FINAL_API}"
  echo ""
  echo "  API 按接口分布:"
  echo "${FINAL_BY_EP}" | while read -r ep cnt; do
    [ -z "$ep" ] && continue
    echo "    ${ep}: ${cnt}"
  done
  echo "=============================================="
} | tee -a "$RESULT_FILE"

cp "$RESULT_FILE" "$SUMMARY_FILE"
echo ""
echo "结果: ${RESULT_FILE}"
echo "汇总: ${SUMMARY_FILE}"
