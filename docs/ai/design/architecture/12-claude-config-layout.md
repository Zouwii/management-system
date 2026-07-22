# Claude CLI 配置目录与权限体系

## 目录结构

```
backend/
├── .claude/
│   └── settings.local.json          ← 项目级权限 (源码管理)
├── runtime/
│   ├── shared/.claude/              ← ⭐ 最先被读到的配置
│   │   ├── settings.local.json      ← 权限 (从 backend/.claude/ 复制)
│   │   ├── skills/                  ← 共享 skills (从 ai/skills/ 复制)
│   │   └── plugins/                 ← 共享 plugins
│   └── users/{safe_owner}/
│       └── .claude/                 ← 预留: 每用户独立配置 (当前未使用)
│
~/.claude/settings.json              ← 用户级 (launcher.sh 每次覆盖写入)
```

## Claude CLI 配置查找顺序

从 **工作目录 (PWD)** 向上遍历，停在**第一个**找到的 `.claude` 目录：

```
PWD: runtime/users/{safe}/workspaces/default/

1. runtime/users/{safe}/workspaces/default/   → 无 .claude
2. runtime/users/{safe}/workspaces/           → 无
3. runtime/users/{safe}/                      → 无 (预留)
4. runtime/users/                             → 无
5. runtime/                                   → 无
6. runtime/shared/.claude/                    → ⭐ 找到! 停止
```

**关键: `runtime/shared/.claude/` 是最先被命中的，必须放 settings.local.json。**

## 三个配置文件

| 文件 | 位置 | 谁写 | 作用 |
|------|------|------|------|
| `settings.local.json` | `backend/.claude/` | Git 源码 | **主配置源**，改权限在这里改 |
| `settings.local.json` | `runtime/shared/.claude/` | 打包复制 | **实际生效**，Claude 读到的是这个 |
| `settings.json` | `~/.claude/` | launcher.sh 写入 | 兜底，项目级没找到才用 |

## 权限格式

```json
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
```

## 修改权限流程

1. 改 `backend/.claude/settings.local.json`
2. `cp` 到 `backend/runtime/shared/.claude/settings.local.json`
3. onekey 部署 → 所有用户生效

## 踩坑记录

- 最初只在 launcher.sh 写 `~/.claude/settings.json`，被项目级 settings.local.json 覆盖
- 旧 `backend/.claude/settings.local.json` 只有 curl + 几个 python3，大量弹权限
- `runtime/shared/.claude/` 比 `backend/.claude/` 更早被找到，两边都得更新
