#!/bin/bash
set -euo pipefail

# 环境变量由 session.py:make_env() 传入，这里不再硬编码
unset ANTHROPIC_AUTH_TOKEN || true
unset OPENAI_API_KEY OPENAI_API_BASE OPENAI_BASE_URL OPENAI_MODEL || true

# ====================== 兜底 PATH ======================
REAL_HOME="${HOME:-}"
if [ -n "${REAL_HOME}" ]; then
  for p in \
    "${REAL_HOME}/.nvm/versions/node/v20.20.2/bin" \
    "${REAL_HOME}/.nvm/versions/node/v20.20.1/bin" \
    "${REAL_HOME}/.nvm/versions/node/v20.20.0/bin" \
    "${REAL_HOME}/.local/bin"
  do
    if [ -d "${p}" ] && [[ ":${PATH}:" != *":${p}:"* ]]; then
      PATH="${p}:${PATH}"
    fi
  done
fi
export PATH

# ====================== 用户隔离 ======================
OWNER_KEY="${AI_OWNER_KEY:-anonymous}"
SAFE_OWNER="$(printf '%s' "${OWNER_KEY}" | sha256sum | awk '{print $1}' | cut -c1-24)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# backend/ 路径（从 ai/terminal/ 向上两级）
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE_DIR="${BACKEND_DIR}/runtime/users/${SAFE_OWNER}/workspaces/default"
mkdir -p "${WORKSPACE_DIR}"

# ====================== 模型选择（环境变量已有模型则跳过） ======================
pick_and_apply_account() {
  # 如果环境变量已设置合法模型，直接使用，跳过交互菜单
  if [ -n "${ANTHROPIC_MODEL:-}" ]; then
    local known=0
    case "${ANTHROPIC_MODEL}" in
      claude*|kimi*|MiniMax*|step*|mimo*|glm*|deepseek*) known=1 ;;
    esac
    if [ "${known}" = "1" ]; then
      CLAUDE_EXTRA_ARGS=(--model "${ANTHROPIC_MODEL}")
      return
    fi
  fi

  local default_num=3
  echo "请选择模型（直接回车默认）："
  echo "1) claude  2) kimi  3) minimax  4) step  5) mimo  6) glm  7) deepseek"
  read -r -p "选择模型 [${default_num}]: " choice
  choice="${choice:-${default_num}}"

  local selected_model="MiniMax-M2.7-highspeed"
  choose_sub_model() {
    local title="$1"
    shift
    local models=("$@")
    local default_sub=1
    echo "${title}"
    local i=1
    for m in "${models[@]}"; do echo "  $i) $m"; i=$((i+1)); done
    read -r -p "子型号 [1]: " sub_choice
    sub_choice="${sub_choice:-1}"
    selected_model="${models[$((sub_choice-1))]}"
  }

  case "${choice}" in
    2) choose_sub_model "kimi 型号：" "kimi-for-coding" "kimi-k2.5" ;;
    3) choose_sub_model "minimax 型号：" "MiniMax-M2.7-highspeed" "MiniMax-M2.7" ;;
    5) choose_sub_model "mimo 型号：" "mimo-v2.5-pro" "mimo-v2.5" ;;
    6) choose_sub_model "glm 型号：" "glm-5.1" "glm-5-turbo" ;;
    7) choose_sub_model "deepseek 型号：" "deepseek-v4-pro" "deepseek-v4-flash" ;;
  esac

  export ANTHROPIC_MODEL="${selected_model}"
  CLAUDE_EXTRA_ARGS=(--model "${selected_model}")
}

pick_and_apply_account

# ====================== 共享 skills ======================
# Source: ai/prompts/ → installed to runtime/shared/.claude/skills/ by install_prompts.sh
SHARED_SKILLS="${BACKEND_DIR}/runtime/shared/.claude/skills"
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
if [ -d "${SHARED_SKILLS}" ]; then
  mkdir -p "${CLAUDE_SKILLS_DIR}"
  for skill_dir in "${SHARED_SKILLS}"/*/; do
    skill_name="$(basename "${skill_dir}")"
    target_link="${CLAUDE_SKILLS_DIR}/${skill_name}"
    if [ -f "${skill_dir}SKILL.md" ] && [ ! -e "${target_link}" ]; then
      ln -s "${skill_dir}" "${target_link}"
      echo "[skill] 已链接: ${skill_name}"
    fi
  done
fi

# ====================== 默认权限：避免每次询问 ======================
mkdir -p "${HOME}/.claude"
cat > "${HOME}/.claude/settings.json" << 'SETEOF'
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(/home/jz/zhr/tb_tool_bt/**)",
      "Write(/home/jz/zhr/tb_tool_bt/**)",
      "Edit(/home/jz/zhr/tb_tool_bt/**)"
    ]
  }
}
SETEOF

# ====================== 启动 ======================
cd "${WORKSPACE_DIR}"
echo "================================================"
echo "工作区已切换到: ${WORKSPACE_DIR}"
echo "当前网关: ${ANTHROPIC_BASE_URL:-未设置}"
echo "当前模型: ${ANTHROPIC_MODEL:-未设置}"
echo "================================================"
echo ""
echo ""

# 传一个初始提示词让 Claude 主动开始对话，而不是等待用户输入。
# 有 skill trigger 时用它作为初始提示，否则用默认提示。
# 注意用位置参数而非 -p，这样 Claude 回复后仍保持交互模式。
if [ $# -gt 0 ]; then
  exec claude --bare "${CLAUDE_EXTRA_ARGS[@]}" "$*"
else
  exec claude --bare "${CLAUDE_EXTRA_ARGS[@]}" "请按 CLAUDE.md 的指引开始"
fi
