#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  TB MCP Setup"
echo "============================================"
echo ""

MCP_FILE="$HOME/.claude/mcp.json"
SETTINGS_FILE="$HOME/.claude/settings.local.json"
MCP_URL="http://172.19.3.79:5200/sse"

# -- 1. get user name --
read -r -p "Enter your Chinese name: " USER_NAME
if [ -z "$USER_NAME" ]; then
  echo "[ERROR] Name cannot be empty"
  exit 1
fi

# -- 2. backup old config --
if [ -f "$MCP_FILE" ]; then
  BACKUP="$MCP_FILE.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$MCP_FILE" "$BACKUP"
  echo "[BACKUP] Old config saved to $BACKUP"
fi

# -- 3. write ~/.claude/mcp.json --
mkdir -p "$HOME/.claude"
cat > "$MCP_FILE" <<EOF
{
  "mcpServers": {
    "tb-mcp": {
      "type": "sse",
      "url": "${MCP_URL}?user_name=${USER_NAME}"
    }
  }
}
EOF
echo "[OK] Written to $MCP_FILE"

# -- 4. enable global MCP in settings --
python3 -c "
import json, os
path = os.path.expanduser('$SETTINGS_FILE')
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data.setdefault('enabledMcpjsonServers', [])
if 'tb-mcp' not in data['enabledMcpjsonServers']:
    data['enabledMcpjsonServers'].append('tb-mcp')
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('[OK] tb-mcp enabled in $SETTINGS_FILE')
"

echo ""
echo "============================================"
echo "  Config:"
cat "$MCP_FILE"
echo "============================================"
echo "  Restart Claude Code to apply ( /exit )"
echo "============================================"
