#!/bin/bash
# 现场问题 A 表断点续拉循环
# 用法: ./sync-onsite-loop.sh <userId>

USER_ID="${1:-}"
if [ -z "$USER_ID" ]; then
    echo "用法: $0 <userId>"
    exit 1
fi

# 绕过代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

BASE="http://172.19.3.79:5002/api/bt"

echo "============================================"
echo "  现场问题 A 表断点续拉"
echo "  userId: $USER_ID"
echo "============================================"

# Step 0: 重置游标
echo ""
echo "[0] 重置游标..."
RESET=$(curl -s -X POST "$BASE/onsite/reset-cursor")
echo "    $RESET"

# Step 1-N: 循环同步
ROUND=1
while true; do
    echo ""
    echo "============================================"
    echo "[$ROUND] 执行同步..."
    echo "============================================"

    RESULT=$(curl -s -X POST "$BASE/onsite/sync" \
        -H "Content-Type: application/json" \
        -d "{\"userId\": \"$USER_ID\"}")

    echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"

    HAS_MORE=$(echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
cursor=d.get('a_sync',{}).get('cursor',{})
print(cursor.get('has_more', False))
" 2>/dev/null)

    if [ "$HAS_MORE" != "True" ]; then
        echo ""
        echo "============================================"
        echo "  ✅ 全量同步完成！共 $ROUND 轮"
        echo "============================================"
        break
    fi

    ROUND=$((ROUND + 1))
    sleep 2
done
