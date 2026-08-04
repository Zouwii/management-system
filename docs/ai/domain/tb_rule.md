# TB 任务单字段规范

## draft.json 完整字段

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| title | string | 是 | ≤ 18 中文字符 | 任务标题 |
| workType | string | 是 | `指派型` / `自主型` / `能力型` | 工时类型 |
| requirementDesc | string | 是 | 支持 `\n` 换行 | 需求描述（背景 + 目标 + 工作范围） |
| outputs | string[] | 是 | 每项格式 `描述(N天)` | 任务产出清单 |
| participationLevel | float | 是 | 等于 outputs 天数之和，必须在固定档位中 | 参与度 |
| dueDate | string | 是 | ISO 8601，截止日 16:00:00 | 截止日期 |
| startDate | string | 是 | ISO 8601，开始日 00:00:00 | 开始日期 |
| parentTaskId | string | 否 | taskId 或 `""` | 父任务 ID |

## draft.json 示例

```json
{
  "title": "优化托盘识别精度",
  "workType": "自主型",
  "requirementDesc": "背景：托盘识别在光照不足时误检率高\n目标：将误检率从 15% 降至 5%",
  "outputs": [
    "数据增强与模型重训(1.0天)",
    "边界 case 测试集构建(0.5天)",
    "A/B 测试与上线验证(0.5天)"
  ],
  "participationLevel": 2.0,
  "dueDate": "2026-06-30T16:00:00+08:00",
  "startDate": "2026-06-03T00:00:00+08:00",
  "parentTaskId": ""
}
```

## 参与度档位

参与度 = 所有产出天数之和。**必须**落在以下固定档位中：

**0.2 / 0.5 / 1.0 / 1.5 / 2.0 / 2.5 / 3.0**

- 单个任务参与度原则上不超过 3.0 人天
- 信息不充分时，优先选保守值

## 产出格式

每项产出格式：`具体描述(N天)`

其中 `N` 为小数，如 `1.0`、`0.5`、`2.5`。产出数量建议 2–5 条。

## 钉钉自定义字段 ID

| 字段名 | customFieldId |
|--------|--------------|
| 需求描述 | `686273700d15b3f835491a2e` |
| 任务性质 | `69d4d037c253ef42e9c31b38` |
| 任务产出 | `6862737e3b781c68b3181925` |

## 校验规则（服务端执行）

| 校验项 | 规则 | 行为 |
|--------|------|------|
| workType | 必须为 指派型/自主型/能力型 | 不合法则拒绝 |
| participationLevel | 必须等于 outputs 天数之和 | 不一致时以 sum 修正 |
| participationLevel | 必须在固定档位中 | 不在档位则告警 |
| title | ≤ 18 中文字符 | 超长则告警 |
| startDate / dueDate | 必须是有效 ISO 8601 | 不合法则拒绝 |
| startDate ≤ dueDate | 开始日期不能晚于截止日期 | 不合法则告警 |

## Teambition Open API v3 — 关联任务

### 查询任务关联的其它任务

```
GET https://open.teambition.com/api/v3/task/{taskId}/objectlinks
```

**请求头**:

| Header | 值 | 说明 |
|--------|-----|------|
| `Content-Type` | `application/json` | |
| `X-Operator-Id` | TB 用户 ObjectId（如 `64df1d979c80be1f3c7476cc`） | 必填，通过 TB 代理传入 body headers |

**响应示例**:

```json
{
  "result": [
    {
      "id": "6900372ab2ffffbf734b4052",
      "parentId": "69003719f1aefb81c0b17963",
      "linkedId": "68fb3c3440d118edb8d1cf2e",
      "linkedType": "task",
      "parent": {
        "id": "69003719f1aefb81c0b17963",
        "content": "交付测试反馈问题处理【10.27-10.31】"
      },
      "linked": {
        "id": "68fb3c3440d118edb8d1cf2e",
        "content": "【宁波包钢】fdn3030，导航精度不足"
      },
      "creatorId": "614a920586f75f5582c18556",
      "created": "2025-10-28T03:23:22.108Z"
    }
  ]
}
```

**字段说明**:

| 字段 | 含义 |
|------|------|
| `linkedId` | 关联任务的 taskId |
| `linkedType` | 关联类型，目前已知值 `task` |
| `linked.content` | 关联任务标题 |
| `parentId` | 当前任务 ID |
| `parent.content` | 当前任务标题 |

**注意**: 此接口需要 `X-Operator-Id`，当前仅通过服务器上的 DingTalk 代理（`tb_proxy.py`）调用，尚未在 management-system 中封装为服务。`linkedType` 目前仅观察到 `task`，但接口可能还支持其它对象类型。
