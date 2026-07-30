# Priority=99 知识库同步记录

> 日期: 2026-07-24 | 脚本: `scripts/kb_raw_sync.py`

## 背景

`kb_workspaces.json` 中 22 个知识库，priority 0-9 已同步入远程 MySQL `kb_storage`，priority=99 的 12 个从未遍历。

本次目标：
1. 估算 12 个 priority=99 workspace 的体量
2. 全量下载节点和文档正文
3. **不入 `api_call_logs`**（裸调钉钉 API，绕过 Flask 监控）
4. **不入 MySQL**（存为 SQLite db 文件）

## 工具

`scripts/kb_raw_sync.py` — 裸调钉钉 API 脚本，直接用 `requests` + 企业 access_token，不经过 Flask、不写 `api_call_logs`。

用法：
```bash
python3 kb_raw_sync.py --estimate-only      # 仅遍历统计
python3 kb_raw_sync.py                      # 全量同步到 SQLite
python3 kb_raw_sync.py --ws <workspace_id> --uid <union_id>
```

## Priority=99 的 12 个知识库

| # | 名称 | workspace_id |
|---|------|-------------|
| 1 | 基线开发部 | `xPar2SAKPb4KZbaV` |
| 2 | 嵌入式和硬件驱动 | `xPar2SD23VJ5p3aV` |
| 3 | 云端软件 | `xwaNdSBPjVRJb20O` |
| 4 | WMS | `lovW2SAVbKrnkGab` |
| 5 | GroupMap | `p48ggS5M2Vrygb87` |
| 6 | 产品技术组【掘金池】 | `QXvd5SmeeEKJex0Z` |
| 7 | 硬件产品 | `9r09jSZd9rWYMW8A` |
| 8 | IT & 运维 | `Gma31SO2ojY7NJ0n` |
| 9 | 〔电气〕研发栈 | `nV06pSopwOEmXyaB` |
| 10 | 〔电气〕叉车组 | `OQ0xySez6RVgAD8B` |
| 11 | 〔电气〕订单组 | `618oRSR15L2oV30L` |
| 12 | 本体测试 | `nb9XJB84VP27DXyA` |

## 权限情况

`list_workspaces` API 返回结果取决于调用者的钉钉权限：

| 用户 | union_id | 可访问的 workspace |
|------|----------|-------------------|
| 王睿 | `Y2w3A88Py5o5IKURjoXiP0QiEiE` | 基线开发部、云端软件、产品技术组【掘金池】 |
| 伍浩贤 | `WfKcTDaMLYp0bLhFHDAAUwiEiE` | 云端软件、GroupMap、产品技术组【掘金池】 |

两人合计覆盖 **4/12**，剩余 8 个均无权限。

## 同步结果

### 基线开发部 `xPar2SAKPb4KZbaV`
- 用户: 王睿
- 节点: 1,100（843 FILE + 257 FOLDER）
- 文档: 466 篇（ALIDOC）
- 失败: 部分 `.axls` 文件 blocks API 报错

### GroupMap `p48ggS5M2Vrygb87`
- 用户: 伍浩贤
- 节点: 885（740 FILE + 145 FOLDER）
- 文档: 16 篇（ALIDOC）
- 失败: 604/620 失败，绝大部分是 `.adoc` / `.axls` 格式，blocks API 不支持

### 产品技术组【掘金池】 `QXvd5SmeeEKJex0Z`
- 用户: 王睿
- 节点: 428（365 FILE + 63 FOLDER）
- 文档: 162 篇

### 云端软件 `xwaNdSBPjVRJb20O`
- 用户: 王睿
- 节点: 270（211 FILE + 59 FOLDER）
- 文档: 153 篇

### 汇总

| 指标 | 值 |
|------|-----|
| workspace | 4 |
| 总节点 | 2,683 |
| FILE 总数 | 2,159 |
| 文档正文 | 797 |
| DB 文件 | `kb_p99.db` (8.7 MB) |
| 总 API 调用 | ~2,000 次 |
| 总耗时 | ~720s |

## API 用量

| 接口 | 用途 | 约次数 |
|------|------|--------|
| `/v2.0/wiki/workspaces` | 获取 rootNodeId | ~4 |
| `/v2.0/wiki/nodes` | 递归遍历目录树 | ~490 |
| `/v1.0/doc/suites/documents/{id}/blocks` | 下载文档正文 | ~1,400 |

> 均不经过 Flask `_log()` → `record_api_call()`，未入 `api_call_logs` 表。

## 已知问题

1. **8 个 workspace 无权限** — 需钉钉管理员将调用用户加入对应知识库
2. **`.adoc` / `.axls` 无法下载** — blocks API 不支持，GroupMap 受影响最大
3. **部分 `.axls` 可解析** — 取决于文件实际类型

## 文件位置

- 服务器: `/home/jz/zhr/tb_tool_bt/kb_p99.db` (8.7 MB)
- 脚本: `scripts/kb_raw_sync.py`
- 本文档: `docs/kb-priority99-sync-record.md`
