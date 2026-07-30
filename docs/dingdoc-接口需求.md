# 钉钉知识库文档导出分析

## 目标

将钉钉知识库文档导出为 Markdown，用于 RAG 检索和 LLM 上下文。

## API 探索结果

### 可用的读接口

| API | 方法 | 路径 | 说明 |
|---|------|------|------|
| 获取文档 blocks | GET | `v1.0/doc/suites/documents/{nodeId}/blocks` | 返回 block 数组，每个 block 有 blockType 和对应 body |
| 列出知识库 | GET | `v2.0/wiki/workspaces` | 获取 workspace 列表 |
| 列出节点 | GET | `v2.0/wiki/nodes` | 获取目录树 |

### 尝试过但不可用的接口

| API | 结果 | 原因 |
|---|------|------|
| `GET v1.0/doc/suites/documents/{id}/content` | NotFound | API 不存在 |
| `GET v2.0/doc/me/suites/documents/{id}/content` | NotFound | API 不存在 |
| `GET v2.0/knowledge/dentry/blocks` | InvalidVersion | knowledge 模块未开通 |
| `GET v1.0/doc/suites/documents/{id}/export` | NotFound | API 不存在 |
| `GET v1.0/doc/suites/documents/{id}/download` | NotFound | API 不存在 |

### 写入接口（仅作对比，证明 markdown 是原生格式）

| API | 结果 |
|---|------|
| `POST v1.0/doc/suites/documents/{id}/overwriteContent` | 存在（缺 Storage.File.Write 权限） |
| `POST v2.0/doc/me/suites/documents/{id}/overwriteContent` | 存在（缺 Document.Document.Write 权限） |

`overwriteContent` 接受 `dataType: "markdown"`，证明钉钉文档原生支持 Markdown，但**读方向没有对应的 GET 接口**。

## 为什么需要 blocks → markdown 转换

钉钉开放平台没有提供「导出文档为 Markdown」的 REST API。唯一可用的读接口是 `get_document_blocks`，返回结构化 block 数组。因此必须自己实现转换。

### blocks API 覆盖范围

| blockType | 是否有内容 | 说明 |
|---------|---------------|------|
| heading | ✅ | level \+ text |
| paragraph | ✅ | text |
| unorderedList | ✅ | text（每条独立 block） |
| orderedList | ✅ | text（每条独立 block，无法递增编号） |
| table | ✅ | cells 二维数组 \+ rowSize/colSize |
| columns | ✅ | children 嵌套 block 数组 |
| blockquote | ❌ | body 始终为 `{}` |
| callout | ❌ | body 始终为 `{}` |
| attachment | ✅ | resourceId / name / size / type，无文件内容 |
| unknown | ❌ | body 始终为 `{}`（图片、分隔线等） |
| code | — | 库中未出现 |

### API 层面丢失的内容

| 内容类型 | 原页面 | API | 影响 |
|------------|---------|---|------|
| callout 高亮块 | `:::` 包裹的需求描述、方案设计、任务清单 | `callout: {}` | **严重**，大量结构化内容丢失 |
| 图片 | `!&#91;image](url)` | `unknown: {}` | 图片 URL 丢失 |
| @mention | `@某人` | 无对应字段 | 人员信息丢失 |
| 任务 checkbox | `&#91; ]` / `&#91;x]` | 无对应 blockType | 任务状态丢失 |
| 内联格式 | 加粗、颜色、链接 | 仅返回纯文本 | 格式丢失 |

### 受影响程度

以 `【四期需求分解】本体与调度协作.adoc`（54 个 block）为例：

| blockType | 数量 | 内容状态 |
|---------|------|------------|
| callout | 16 | **全部为空** — 需求描述/方案设计/任务清单丢失 |
| heading | 13 | 完整 |
| columns | 13 | 完整（需递归 children） |
| paragraph | 10 | 完整 |
| unknown | 2 | 空（图片） |
| table | 1 | 完整 |

## 当前方案
```
钉钉 API: get_document_blocks
       │
       ▼  blocks 数组 (JSON)
       │
       ▼  parser.py: blocks_to_markdown()
       │
       ▼  Markdown → kb_documents.content
                  raw_json → kb_documents.raw_json

```

### parser 状态
- [x] table cells 二维数组正确转换（修复中）
- [ ] columns children 递归展开
- [ ] 有序列表编号递增（低优，渲染器兼容）
- [ ] callout / blockquote / unknown — API 无数据，parser 无法补救

### 存储策略
- `content`（MEDIUMTEXT）：parser 转换后的 Markdown
- `raw_json`（MEDIUMTEXT）：完整 API 回包，parser 修复后可重新生成

## 替代方案评估

| 方案 | 可行性 | 问题 |
|------|---------|------|
| 页面导出 Markdown API | ❌ | 不存在 |
| 导出 docx/pdf 再转换 | ⚠️ | 需额外权限，链路长、保真度低 |
| Headless browser 抓页面 | ⚠️ | 需 puppeteer 环境，复杂度高 |
| 申请 knowledge 模块权限 | ⚠️ | 不确定是否有更好读接口 |

## 结论

在钉钉开放平台提供 Markdown 导出接口之前，`blocks → markdown` 是唯一可行路径。heading/paragraph/table/list 等核心内容可完整保留，callout/image/checkbox 等富文本在 API 层面就已丢失。丢失内容通过 `raw_json` 保留原始数据，未来 API 升级后可重解析。

---

## 附录：页面 vs API 完整对比

以 `【四期需求分解】本体与调度协作.adoc` 为例。

### 对比总览

|  | 原页面 (54 blocks 等价结构) | API get\_document\_blocks |
|---|----------------------------------|-------------------------|
| 修订记录表格 | ✅ 完整 | ✅ 完整（cells 2D） |
| 项目时间 callout | ✅ `:::` 包含时间表 | ❌ `callout: {}` |
| 项目人员 @mention | ✅ `@程卓``@伍浩贤` 等 | ❌ 纯文本，无 mention |
| 需求描述 paragraphs | ✅ 完整 | ✅ 完整 |
| 方案设计 callout | ✅ `&#91;钉子]` 含详细方案 | ❌ `callout: {}` |
| 接口协议 columns | ✅ 含有序/无序列表 | ✅ columns.children 有内容 |
| 任务清单 callout | ✅ `&#91; ]` checkbox 含负责人 | ❌ `callout: {}` |
| 截图/图片 | ✅ 多张图片 | ❌ `unknown: {}`，URL 丢失 |

### 原文拆解
```
# 【四期需求分解】本体与调度协作

| 修订记录 | 作者 | 时间 | 说明 |
| --- | --- | --- | --- |
| V1.0 | @何鸿颉 | 2025-12-09 | 初版 |

# 开发说明
## 版本信息
开发基础版本：2509 | 合入版本：2603

## 项目时间
:::                          ← callout 开始
软件功能交付：2026-01-23     ← 全部丢失
测试用例评审：2026-01-26
测试完成时间：2026-02-05
验收时间：2026-02-06
:::                          ← callout 结束

## 项目人员
软件测试：@程卓              ← mention 丢失
研发项目经理：@伍浩贤
开发人员：@何鸿颉 @琚玲 ...

# 需求清单

## 货架腿过滤适配

:::
[资料] 需求描述              ← callout 全部丢失
背景：在本体调度协作三期中...
- 但是scan-filter货架腿过滤...
:::
[钉子] 方案设计              ← callout 全部丢失
scan-filter货架腿过滤使用安全模块统一下发...
:::
[资料] 接口协议              ← columns 有内容，需递归
- 根据最新讨论结果：
  - 由导航后端节点直接处理...
:::
[钉子] 任务清单              ← callout 全部丢失


[ ] 安全模块发布货架TF       ← checkbox 丢失




[ ] 导航统一读取货架TF...


:::

## 可行域相关功能优化
(同上模式，6 个 callout 全部为空)

## 优化调度与本体的裁断阈值
:::
[资料] 接口协议
![image](https://...oss...)   ← unknown: {}，URL 丢失
:::

```

### API 同段落实际返回值

对应的 blocks（节选）：
```json
// ✅ 表格 — 结构完整
{ "blockType": "table",
  "table": {
    "cells": [
      ["修订记录", "作者", "时间", "说明"],
      ["V1.0", "","","初版"]
    ], "colSize": 4, "rowSize": 3
  }
}

// ❌ callout — 正文丢失
{ "blockType": "callout", "index": 10,
  "callout": {}                // 项目时间全部内容丢失
}

// ❌ callout — 方案设计丢失
{ "blockType": "callout", "index": 19,
  "callout": {}                // 货架腿过滤方案设计丢失
}

// ⚠️ columns — 内容在 children 里，需递归
{ "blockType": "columns", "index": 18,
  "columns": {
    "size": 1,
    "children": [[
      { "blockType": "paragraph",   "paragraph": { "text": "需求描述" } },
      { "blockType": "paragraph",   "paragraph": { "text": "背景：..." } },
      { "blockType": "unorderedList","unorderedList": { "text": "但是scan-filter..." } }
    ]]
  }
}

// ❌ unknown — 图片丢失
{ "blockType": "unknown", "index": 1,
  "unknown": {}                 // 接口协议的截图，URL 丢失
}

```

### 内容恢复率估算

以这篇文档的 54 个 block 计算（按实际内容占比而非 block 数量）：

| 可恢复 | 不可恢复 |
|---------|------------|
| heading ×13、paragraph ×10、table ×1、columns.children 内的 list ×N | callout ×16（全部需求描述/方案/任务清单）、unknown ×2（图片） |

**估计可恢复 ~40%，丢失 ~60%**。丢失的主要是 callout 内的核心业务内容（需求描述、方案设计、任务清单）。



[【四期需求分解】本体与调度协作](https://alidocs.dingtalk.com/i/nodes/ZX6GRezwJl7KPA5zhREeXpG5VdqbropQ?iframeQuery=utm_source%3Dportal%26utm_medium%3Dportal_recent)


[【四期需求分解】本体与调度协作.md](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/4EZlwe4maY5kXqxA/att/1308096b-a40e-4251-b2ea-0f8efc15322a.md?Expires=1785405837&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=PEP25UQ3y3cY9al3dlU039bpnew%3D)




```json
{
  "ok": true,
  "data": [
    {
      "blockType": "unknown",
      "index": 0,
      "id": "megjlpf9t17tu3locm",
      "unknown": {}
    },
    {
      "blockType": "table",
      "index": 1,
      "id": "lz0pg34u765jhy33s33",
      "table": {
        "cells": [
          [
            "修订记录",
            "作者",
            "时间",
            "说明"
          ],
          [
            "V1.0",
            "",
            "",
            "初版"
          ],
          [
            "",
            "",
            "",
            ""
          ]
        ],
        "colSize": 4,
        "rowSize": 3
      }
    },
    {
      "heading": {
        "level": "heading-1",
        "text": "开发说明"
      },
      "blockType": "heading",
      "index": 2,
      "id": "mei7xsfeakjqltacydp"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "版本信息"
      },
      "blockType": "heading",
      "index": 3,
      "id": "mizku961dr0zshm41s9"
    },
    {
      "paragraph": {
        "text": "开发基础版本：2509（合入本体与调度协作三期后版本）"
      },
      "blockType": "paragraph",
      "index": 4,
      "id": "merwofn98c4g11amwgv"
    },
    {
      "paragraph": {
        "text": "合入版本：2603（暂定）"
      },
      "blockType": "paragraph",
      "index": 5,
      "id": "mg3jslevbeq0v5ir784"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "项目时间"
      },
      "blockType": "heading",
      "index": 6,
      "id": "mizkuertxtpgi4yfz"
    },
    {
      "paragraph": {
        "text": "导入时间："
      },
      "blockType": "paragraph",
      "index": 7,
      "id": "mev1apkcl9rjlgaywd"
    },
    {
      "paragraph": {
        "text": "公示时间："
      },
      "blockType": "paragraph",
      "index": 8,
      "id": "mei7xsk0xnilcjzz1ar"
    },
    {
      "paragraph": {
        "text": "分解时间："
      },
      "blockType": "paragraph",
      "index": 9,
      "id": "mei8041zha1vh91ux6"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 10,
      "id": "mev1a0314nvcysizduc"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "项目人员"
      },
      "blockType": "heading",
      "index": 11,
      "id": "mizkuqc07m5rnhjp17c"
    },
    {
      "paragraph": {
        "text": "软件测试："
      },
      "blockType": "paragraph",
      "index": 12,
      "id": "mizkun8k8bfs35rbe1h"
    },
    {
      "paragraph": {
        "text": "研发项目经理："
      },
      "blockType": "paragraph",
      "index": 13,
      "id": "mev5n89nym65yozsv9"
    },
    {
      "paragraph": {
        "text": "开发人员："
      },
      "blockType": "paragraph",
      "index": 14,
      "id": "me9oasjuuvfm6ku70f"
    },
    {
      "paragraph": {
        "text": ""
      },
      "blockType": "paragraph",
      "index": 15,
      "id": "miy0jydv1equrb6jssw"
    },
    {
      "heading": {
        "level": "heading-1",
        "text": "需求清单"
      },
      "blockType": "heading",
      "index": 16,
      "id": "me9oawlbkj5zipnati"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "货架腿过滤适配"
      },
      "blockType": "heading",
      "index": 17,
      "id": "me9ct1u3h7magmsr6mr"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "m7y7uuer03i1s5rnws8u",
              "parentId": "m7y7uuers0itlhxhepi"
            },
            {
              "paragraph": {
                "text": "背景：在本体调度协作三期中，安全模块将转盘角度与货架实际角度叠加后，对外发布统一的货架角度，导航现在已经使用"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "m7y7uuers4dyg6z279",
              "parentId": "m7y7uuers0itlhxhepi"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "miwqkq3qpj40pwnozq",
              "unorderedList": {
                "text": "但是scan-filter货架腿过滤和前端显示的货架腿过滤区域目前使用的是转盘角度，导致过滤和显示会出问题。需要改成由安全模块统一提供的货架角度。"
              },
              "parentId": "m7y7uuers0itlhxhepi"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 18,
      "id": "m7y7uuers0itlhxhepi"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 19,
      "id": "miwm0dklk9arkr3qhtb"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "接口协议"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "m7y7uuesljqcknc3uz",
              "parentId": "m7y7uuescv5e9b3unxj"
            },
            {
              "blockType": "unorderedList",
              "index": 1,
              "id": "mjiehy590n3er8y7aq4p",
              "unorderedList": {
                "text": "根据最新讨论结果："
              },
              "parentId": "m7y7uuescv5e9b3unxj"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "mjz6wkdkmpzxquh7tt8",
              "unorderedList": {
                "text": "由导航后端节点直接处理货架角度后发布给前端（nav-net端口：8850）"
              },
              "parentId": "m7y7uuescv5e9b3unxj"
            },
            {
              "blockType": "unorderedList",
              "index": 3,
              "id": "mjiekcfjb79pcqpk29t",
              "unorderedList": {
                "text": "仍使用websocket发布，字段：ws.stream.shelfAngle，格式：数值（度）"
              },
              "parentId": "m7y7uuescv5e9b3unxj"
            },
            {
              "blockType": "unorderedList",
              "index": 4,
              "id": "mjijtaw9lrs3f30ezn",
              "unorderedList": {
                "text": "安全模块下发货架TF：base_footprint->base_shelf"
              },
              "parentId": "m7y7uuescv5e9b3unxj"
            },
            {
              "blockType": "unorderedList",
              "index": 5,
              "id": "mjz6wb8y0aq03ah98586",
              "unorderedList": {
                "text": "供scan-filter货架腿过滤使用"
              },
              "parentId": "m7y7uuescv5e9b3unxj"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 20,
      "id": "m7y7uuescv5e9b3unxj"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 21,
      "id": "miwm18z1v3mtwbuxwf"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "可行域相关功能优化"
      },
      "blockType": "heading",
      "index": 22,
      "id": "miws252nz38o06h1lb"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "miws252n19yfta0x79e",
              "parentId": "miws252nz17jtise75"
            },
            {
              "paragraph": {
                "text": "背景：在本体调度协作前几期中，针对可行域进行了大量的优化与改进，这一次将参考友商使得可行域更加的直观好用，主要包括以下几点优化："
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "miws252nzj2zwlopxae",
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "miws4g74rzt9wnmbbl",
              "unorderedList": {
                "text": "异常处理优化：本期需实现没有接收到可行域或者接收可行域异常，安全模块需要停车告警。"
              },
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 3,
              "id": "miwt0trw74xdz8qpa9o",
              "unorderedList": {
                "text": "路径可行域优化：在实际使用时发现安全偏移距离的相对概念并不直观，用户难以观测当前这条道路实际允许多少安全偏移距离，从而配置为安全偏移值，故希望将这个参数改为像可行域宽度一样的绝对距离，同时旋转空间可行域没有协议表示。"
              },
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 4,
              "id": "miwt34dokppi8kxt95h",
              "unorderedList": {
                "text": "增加全新【路宽】字段，代替原有【安全偏移距离】"
              },
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 5,
              "id": "miwt38d1h63tlpmlqkt",
              "unorderedList": {
                "text": "本体与调度使用全新路宽字段处理可行域"
              },
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 6,
              "id": "miwup4yhc8rozks759",
              "unorderedList": {
                "text": "调度采用全新协议下发可行域，考虑旋转空间"
              },
              "parentId": "miws252nz17jtise75"
            },
            {
              "blockType": "unorderedList",
              "index": 7,
              "id": "miwt40xowqh0ztmrxqm",
              "unorderedList": {
                "text": "去掉导航精度不满足二次请求精度调整逻辑"
              },
              "parentId": "miws252nz17jtise75"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 23,
      "id": "miws252nz17jtise75"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 24,
      "id": "miws252o3ympwzpxg6g"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "接口协议"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "miws252o05bcrlfxp7l7",
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 1,
              "id": "miws252oktkm2vopio",
              "unorderedList": {
                "text": "调度使用路宽概念："
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "miwtfucp7f0o466u59",
              "unorderedList": {
                "text": "调度使用路宽左右均分道路；"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 3,
              "id": "miwtfwfsnc4hwuokr0s",
              "unorderedList": {
                "text": "如果设置路宽小于调度默认车体尺寸（车体尺寸+膨胀区域），调度应该禁用该路线；"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 4,
              "id": "miwtg1r8dcfkcu2lbt",
              "unorderedList": {
                "text": "路宽默认值是0，但0是无效值，对于设置为0的路径，调度在下发可行域时按照调度默认车体尺寸下发路宽给单机；"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 5,
              "id": "ml0o6lrml7w61abkea8",
              "unorderedList": {
                "text": "调度判断空间占用会用上在车体footprint加上空间管理膨胀后的最终尺寸"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 6,
              "id": "ml0o0ob19c3m91c3u17",
              "unorderedList": {
                "text": "本体使用路宽概念："
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 7,
              "id": "ml0o0wq34hdzkhy6vq4",
              "unorderedList": {
                "text": "路宽（width）就是可行域的唯一尺寸，本体检测超出可行域并不包括调度所膨胀后的footprint尺寸，仅考虑真实footprint尺寸，故本体在单机下发任务时，可行域宽度应为路宽（width）尺寸；"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 8,
              "id": "ml0o4fnx00b6zg1jc6xse",
              "unorderedList": {
                "text": "路宽默认值是0，但0是无效值，对于设置为0的路径，可行域按照 footprint 尺寸+本体机型膨胀尺寸计算路宽下发给 costmap；"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 9,
              "id": "ml0o6d24ylz4zbs7up",
              "unorderedList": {
                "text": "单机仅在终点和旋转时需要考虑三代机型中设置的膨胀，用于生成终点可行域和外接圆可行域"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 10,
              "id": "miwthl891ftq63sqwx4",
              "unorderedList": {
                "text": "调度下发全新可行域给本体："
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 11,
              "id": "miwti4j8b0ixsebkox5",
              "unorderedList": {
                "text": "使用多边形（map下的多边形顶点坐标）+圆（map下的圆心坐标+半径）来下发全新可行域"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 12,
              "id": "miwtizqvnsydsvsksrc",
              "unorderedList": {
                "text": "下发可行域有重叠部分，本体需要取并集使用"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 13,
              "id": "miwtn9o60u933tr4ywg9",
              "unorderedList": {
                "text": "【路宽】表示在该条路线上允许的可行域大小"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 14,
              "id": "misqos51u4xfmbn9ui",
              "unorderedList": {
                "text": "终点上的左右可行域大小使用路宽数值。"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 15,
              "id": "misqrftcpe43sujrdvg",
              "unorderedList": {
                "text": "终点上的前后可行域大小使用全局膨胀数值。"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 16,
              "id": "miy18i7c360pzbvv6h6",
              "unorderedList": {
                "text": "前端【路宽】字段后端数据可沿用现有width属性"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 17,
              "id": "miy1assy72pxxxrw2gh",
              "unorderedList": {
                "text": ""
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 18,
              "id": "miy1ay6dm7op2y910w",
              "unorderedList": {
                "text": "隐藏【安全偏移距离】字段"
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 19,
              "id": "mizlt5u4vdqwquleabj",
              "unorderedList": {
                "text": "下发costmap可行域："
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 20,
              "id": "mizlte9dip356xhy9ur",
              "unorderedList": {
                "text": ""
              },
              "parentId": "miws252ocwdpgv142im"
            },
            {
              "blockType": "unorderedList",
              "index": 21,
              "id": "mj87n7iap29dg4dlhd",
              "unorderedList": {
                "text": "不宜太快，防止costmap频繁更新可行域造成CPU占用过高"
              },
              "parentId": "miws252ocwdpgv142im"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 25,
      "id": "miws252ocwdpgv142im"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 26,
      "id": "miws252olajh4eg3zk"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "统一车型，车体尺寸，车体膨胀数据源"
      },
      "blockType": "heading",
      "index": 27,
      "id": "mj0ud2uuo384xlr24qq"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mj0ud2uwzb26j5jmqlm",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": "背景："
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "mj0ud2uwg0llvggvch7",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "orderedList",
              "index": 2,
              "id": "mj0t396e87058g7bwyt",
              "orderedList": {
                "text": "调度通过mapCloud/getMapData从地图获取车型名称和货架尺寸"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 3,
              "id": "mj0t1nn64d93rxwwski",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 4,
              "id": "mj0t5xslok1tma8u5z",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "orderedList",
              "index": 5,
              "id": "mj0t1nvva4h6cnk92e",
              "orderedList": {
                "text": "调度从空间管理获取车体尺寸"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "orderedList",
              "index": 6,
              "id": "mj0t3m026ngrugqyxrj",
              "orderedList": {
                "text": "调度从空间管理获取车体膨胀"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 7,
              "id": "mj0tb8135qiz36mee7p",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": "这样会造成两个问题："
              },
              "blockType": "paragraph",
              "index": 8,
              "id": "mj0ug9zlhd2z7p2eiwa",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 9,
              "id": "mj0vw4u2fqam0pmv9xg",
              "unorderedList": {
                "text": "一是车体尺寸调度和本体存在两个地方配置，会导致同一车型尺寸不一致的问题。"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 10,
              "id": "mj0vwgmqp4udnpoc2kr",
              "unorderedList": {
                "text": "二是车体膨胀只有调度能用，如果单机导航使用可行域的话，无法获取车体膨胀数据，会导致可行域和调度下发的不一致。"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 11,
              "id": "mj0w7o4kywny136h6i",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": "最终如何将车型，车体尺寸，车体膨胀，货架数据统一？"
              },
              "blockType": "paragraph",
              "index": 12,
              "id": "mj0t4w0mdp7dxohmg7s",
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 13,
              "id": "mj0t2qz34b9qgmmirya",
              "unorderedList": {
                "text": "车型：已有功能。目前可以在地图中添加车型，表示该地图允许哪些车在这上面运行，但是现在如果非允许车型下载了该地图并使用，没有明确的报错信息"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 14,
              "id": "mj0ubnhuadr9togyrdw",
              "unorderedList": {
                "text": "货架数据：已有功能"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 15,
              "id": "mj0w4z2awynf4527328",
              "unorderedList": {
                "text": "车体尺寸：调度能直接从三代车型中获取数据 or 地图能从三代车型中同步获取车体尺寸 or 在添加车型中增加车体尺寸编辑"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "blockType": "unorderedList",
              "index": 16,
              "id": "mj0ub8tuij9rj2xjnd",
              "unorderedList": {
                "text": "车体膨胀：调度能直接从三代车型中获取数据 or 地图能从三代车型中同步获取车体膨胀 or 在添加车型中增加车体膨胀编辑"
              },
              "parentId": "mj0ud2uwe12o7vrvhop"
            },
            {
              "paragraph": {
                "text": "暂无解决方案。"
              },
              "blockType": "paragraph",
              "index": 17,
              "id": "mj0way8rar65kpaqi09",
              "parentId": "mj0ud2uwe12o7vrvhop"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 28,
      "id": "mj0ud2uwe12o7vrvhop"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 29,
      "id": "mj0ud2uw392yg3xyfyl"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 30,
      "id": "mj0ud2uxxmjg0qmanpi"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "优化调度与本体的裁断阈值"
      },
      "blockType": "heading",
      "index": 31,
      "id": "miwuw55vyt4trffjsum"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "miwuw55v10fl4zwp6va",
              "parentId": "miwuw55vvmpb0nbzhe"
            },
            {
              "paragraph": {
                "text": "背景：在三期开发中，针对调度与本体针对原子指令的裁断做出了阈值统一，采取如下方式进行裁断，但是这个阈值是一个确定的硬参数。期望将实际应用的可行域参与该阈值的动态调整，根据实时变化的可行域，动态调整裁断阈值，实现在直角线路上自主决策原地旋转还是顺滑过弯，增加运行效率。"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "miwuw55vyjmtqjirgwj",
              "parentId": "miwuw55vvmpb0nbzhe"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "miwuw55v2dnrsenmjtt",
              "unorderedList": {
                "text": "现阶段暂时采用更大的阈值进行处理"
              },
              "parentId": "miwuw55vvmpb0nbzhe"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 32,
      "id": "miwuw55vvmpb0nbzhe"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 33,
      "id": "miwuw55vm3pcbxxs1w"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "接口协议"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "miwuw55vb5q20u9lv8",
              "parentId": "miwuw55vpl4yke82onl"
            },
            {
              "blockType": "unknown",
              "index": 1,
              "id": "mfui6pqtnx9m5qyddc",
              "parentId": "miwuw55vpl4yke82onl",
              "unknown": {}
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 34,
      "id": "miwuw55vpl4yke82onl"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 35,
      "id": "miwuw55wr3pbxb4n0rb"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "Carly货架管理界面增加坐标系说明"
      },
      "blockType": "heading",
      "index": 36,
      "id": "mix2rgt15x6o0zlkhbe"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mix2rgt24h56pifud1c",
              "parentId": "mix2rgt2gx5omp8ppwr"
            },
            {
              "paragraph": {
                "text": "背景：在三期开发中，统一了无码与有码货架的所有定义，但仅在方案设计上做出了相关图例说明，在实际货架模板界面并没有直观的描述。"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "mix2rgt2eqv9ao658mg",
              "parentId": "mix2rgt2gx5omp8ppwr"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "mix2t9zlef2cq0npvs7",
              "unorderedList": {
                "text": "期望将坐标系图例直接加入到货架模板管理页面中，用于直观的说明前向与侧向代表的实际含义。"
              },
              "parentId": "mix2rgt2gx5omp8ppwr"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 37,
      "id": "mix2rgt2gx5omp8ppwr"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 38,
      "id": "mix2rgt3v4o1buf8r3j"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 39,
      "id": "mix2rgt3fy16oulak18"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "调度与本体任务冗余指令合并逻辑优化"
      },
      "blockType": "heading",
      "index": 40,
      "id": "mix303pm0dza0hhqsfn6"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mix303poif591pzbg4",
              "parentId": "mix303po3anw0ru05vt"
            },
            {
              "paragraph": {
                "text": "背景：调度规划的任务中存在一些需要合并的情况，但是导航在某些情况下的合并会导致任务出现非法，故调度和导航对于合并处理需要进行相关的优化。"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "mix303pol1eycvk1ky",
              "parentId": "mix303po3anw0ru05vt"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 2,
              "id": "mix3g3m7pat1h3mmvm",
              "parentId": "mix303po3anw0ru05vt"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 41,
      "id": "mix303po3anw0ru05vt"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 42,
      "id": "mix303pp4hrftsyr4aa"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "接口协议"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mix303pp5ig22dcejd9",
              "parentId": "mix303pp1d8qse746vd"
            },
            {
              "blockType": "unorderedList",
              "index": 1,
              "id": "mix33mgeztgcemuvsta",
              "unorderedList": {
                "text": "loc上报沿用现有rostopic：/move_task_server/route_params，采用<std_msgs::String>消息格式，存储形式为\"<上一个点loc，下一个点loc>\"，例如\"<1000010,10000011>\""
              },
              "parentId": "mix303pp1d8qse746vd"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 43,
      "id": "mix303pp1d8qse746vd"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 44,
      "id": "mix303ppb7rsr9uaf4p"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "任务开始时货架与底盘角度和初始角度不一致需进行旋转上道"
      },
      "blockType": "heading",
      "index": 45,
      "id": "mix3m1azu5mlsyjfk0k"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mix3m1b0aknicurt6w",
              "parentId": "mix3m1b03j4mfy07tx6"
            },
            {
              "paragraph": {
                "text": "背景：每次接收到新任务时，如果货架或者底盘角度朝向和调度下发的初始角度任务不一致（90°倍数的离散化角度），调度会直接规划基于当前topo点位的角度进行MOVE的指令，导航大概率会走一条圆弧的轨迹出来。"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "mix3m1b0j3p90lxlssh",
              "parentId": "mix3m1b03j4mfy07tx6"
            },
            {
              "blockType": "unorderedList",
              "index": 2,
              "id": "mix3nj83yfz7rj642t",
              "unorderedList": {
                "text": "henkel上加了任务起始阶段判断角度一致性，如果不一致，导航插入原地旋转任务进行调整。"
              },
              "parentId": "mix3m1b03j4mfy07tx6"
            },
            {
              "blockType": "unorderedList",
              "index": 3,
              "id": "mixxhrgji5580ep3yk",
              "unorderedList": {
                "text": "本期期望调度能识别到这种情况，本体不应篡改调度指令"
              },
              "parentId": "mix3m1b03j4mfy07tx6"
            },
            {
              "paragraph": {
                "text": ""
              },
              "blockType": "paragraph",
              "index": 4,
              "id": "mix3m1b0gffzvhvi81o",
              "parentId": "mix3m1b03j4mfy07tx6"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 46,
      "id": "mix3m1b03j4mfy07tx6"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 47,
      "id": "mix3m1b1u4bb27r0ks"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "接口协议"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mix3m1b1uuingi88ygi",
              "parentId": "mix3m1b1ubak3snibi"
            },
            {
              "blockType": "unorderedList",
              "index": 1,
              "id": "mix3m1b1knpl8l2b8q",
              "unorderedList": {
                "text": "调度应额外将当前小车状态考虑进规划，并在需要旋转上道时插入一个ROTATE在任务起始部分"
              },
              "parentId": "mix3m1b1ubak3snibi"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 48,
      "id": "mix3m1b1ubak3snibi"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 49,
      "id": "mix3m1b1a8q2zmp6oy9"
    },
    {
      "heading": {
        "level": "heading-2",
        "text": "Henkel优化合入主干"
      },
      "blockType": "heading",
      "index": 50,
      "id": "mj8594q1s0qo3d1a18"
    },
    {
      "columns": {
        "size": 1,
        "children": [
          [
            {
              "paragraph": {
                "text": "需求描述"
              },
              "blockType": "paragraph",
              "index": 0,
              "id": "mj859hqcpxsiiuf7hqo",
              "parentId": "mj859hqctygafpaw65"
            },
            {
              "paragraph": {
                "text": "背景：针对澳洲Henkel货到人场景出现的一些问题进行了优化，期望可以将该优化内容合入主干。"
              },
              "blockType": "paragraph",
              "index": 1,
              "id": "mj859hqcu6aejnuyzon",
              "parentId": "mj859hqctygafpaw65"
            },
            {
              "paragraph": {
                "text": "详见文档："
              },
              "blockType": "paragraph",
              "index": 2,
              "id": "mj85cphcv3k53padg3n",
              "parentId": "mj859hqctygafpaw65"
            }
          ]
        ]
      },
      "blockType": "columns",
      "index": 51,
      "id": "mj859hqctygafpaw65"
    },
    {
      "callout": {},
      "blockType": "callout",
      "index": 52,
      "id": "mj859hqe6q4jv4ahcj"
    },
    {
      "paragraph": {
        "text": ""
      },
      "blockType": "paragraph",
      "index": 53,
      "id": "mj88epwoqvaog6xsu3f"
    }
  ]
}
```


