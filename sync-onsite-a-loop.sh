#!/bin/bash
# 现场问题 A 表断点续拉循环（仅 A 表，不触发 B 表）
# 用法: ./sync-onsite-a-loop.sh <userId>

USER_ID="${1:-}"
if [ -z "$USER_ID" ]; then
    echo "用法: $0 <userId>"
    exit 1
fi

BASE="http://127.0.0.1:5002/api/bt"

echo "============================================"
echo "  现场问题 A 表断点续拉（仅A表）"
echo "  userId: $USER_ID"
echo "============================================"

# 先查当前游标
echo ""
echo "[0] 当前游标状态..."
curl -s "$BASE/onsite/cursor" | python3 -m json.tool 2>/dev/null

ROUND=1
while true; do
    echo ""
    echo "============================================"
    echo "[$ROUND] 执行 A 表同步..."
    echo "============================================"

    RESULT=$(curl -s -X POST "$BASE/onsite/sync-a" \
        -H "Content-Type: application/json" \
        -d "{\"userId\": \"$USER_ID\"}")

    echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"

    HAS_MORE=$(echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
cursor=d.get('cursor',{})
print(cursor.get('has_more', False))
" 2>/dev/null)

    if [ "$HAS_MORE" != "True" ]; then
        echo ""
        echo "============================================"
        echo "  ✅ A 表全量同步完成！共 $ROUND 轮"
        echo "============================================"
        break
    fi

    ROUND=$((ROUND + 1))
    sleep 2
done
