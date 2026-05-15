#!/bin/bash
set -euo pipefail

# 环境变量由 session.py:make_env() 传入，这里不再硬编码
unset ANTHROPIC_AUTH_TOKEN || true

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
      PATH="${PATH}:${p}"
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

# ====================== 模型选择（始终显示菜单） ======================
pick_and_apply_account() {
  local default_num=3
  # 如果环境变量已有模型，预选对应菜单项
  if [ -n "${ANTHROPIC_MODEL:-}" ]; then
    case "${ANTHROPIC_MODEL}" in
      claude*)   default_num=1 ;;
      kimi*)     default_num=2 ;;
      MiniMax*)  default_num=3 ;;
      step*)     default_num=4 ;;
      mimo*)     default_num=5 ;;
      glm*)      default_num=6 ;;
      deepseek*) default_num=7 ;;
    esac
  fi
  echo "请选择模型（直接回车默认）："
  echo "1) claude  2) kimi  3) minimax  4) step  5) mimo  6) glm  7) deepseek"
  read -r -p "选择模型 [${default_num}]: " choice
  choice="${choice:-${default_num}}"

  local selected_model="${ANTHROPIC_MODEL:-MiniMax-M2.7-highspeed}"
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

# ====================== 启动 ======================
cd "${WORKSPACE_DIR}"
echo "================================================"
echo "工作区已切换到: ${WORKSPACE_DIR}"
echo "当前网关: ${ANTHROPIC_BASE_URL:-未设置}"
echo "当前模型: ${ANTHROPIC_MODEL:-未设置}"
echo "================================================"
echo ""
echo "💡 输入「创建tb单」「创建钉钉单」「创建任务」开始创建任务草稿"
echo ""

exec claude "${CLAUDE_EXTRA_ARGS[@]}" "$@"
