# AI 1.0 数据契约

这个文件记录 AI 1.0 计划使用的接口入参和返回结构。

字段名先保持英文，方便前后端代码直接使用；说明文字使用中文，方便维护。

## 生成任务草稿请求

用途：用户输入一段任务描述，后端返回结构化任务草稿。

```json
{
  "prompt": "用户输入的任务背景",
  "context": {
    "targetUserId": "可选，目标用户 ID",
    "targetName": "可选，目标用户名称"
  }
}
```

## 生成任务草稿响应

```json
{
  "draft": {
    "title": "任务标题",
    "taskType": "开发实现任务",
    "workType": "指派型",
    "requirementDesc": "需求描述",
    "outputs": ["交付物 1"],
    "participationLevel": 1
  },
  "missingFields": [],
  "confidence": 0.8
}
```

字段说明：

- `draft`：AI 生成的任务草稿。
- `missingFields`：AI 判断还缺少的信息，例如 `outputs`、`participationLevel`。
- `confidence`：AI 对草稿完整性的粗略置信度，范围为 `0` 到 `1`。

## 创建任务单请求

用途：用户确认草稿后，后端创建真实 TB 任务单。

当前后端 1.0 路由：

- `POST /api/bt/ai/create_mission/payload`：只生成钉钉 create payload，方便调试模板。
- `POST /api/bt/ai/create_mission`：真正调用钉钉接口创建任务。
- `POST /api/dashboard/ai-task-ticket`：前端 AI 创建任务单按钮使用的兼容入口。

```json
{
  "userId": "发起创建接口的钉钉用户 ID",
  "executorId": "任务执行人钉钉用户 ID",
  "draft": {
    "title": "任务标题",
    "taskType": "开发实现任务",
    "workType": "指派型",
    "requirementDesc": "需求描述",
    "outputs": ["交付物 1"],
    "participationLevel": 1
  }
}
```

说明：

- `userId` 用于拼接钉钉创建任务接口路径。
- `executorId` 是创建出来的任务执行人。
- 如果不传 `template`，后端默认使用本体开发部软件开发任务模板。
- 可以通过 `template` 覆盖 `projectId`、`scenariofieldconfigId`、`stageId`、`tasklistId`、`taskflowstatusId`。
- 如果草稿里有 `workType`，后端会尽量转换成任务性质自定义字段 `customfields`。

## 创建任务单模板字段

默认模板来自当前本体开发部软件开发任务：

```json
{
  "projectId": "647854bc4a622b2e3199fa5a",
  "scenariofieldconfigId": "647854bcd999c893061ef8b5",
  "stageId": "647854bcd999c893061ef8a1",
  "tasklistId": "647854bcd999c893061ef898",
  "taskflowstatusId": "680a31478c1bdfc448d36ed0",
  "visible": "members"
}
```

## 创建任务单响应

```json
{
  "success": true,
  "taskId": "TB-12345",
  "taskUrl": "https://www.teambition.com/project/.../task/...",
  "message": "已创建任务单",
  "requestPayload": {
    "content": "任务标题",
    "executorId": "执行人 ID",
    "projectId": "项目 ID"
  }
}
```

## 任务分析请求

用途：根据查看对象和时间范围，分析数据库中已有任务数据。

```json
{
  "target": "user_id 或 ALL",
  "startDate": "2026-04-01T00:00:00",
  "endDate": "2026-06-30T23:59:59"
}
```

## 任务分析响应

```json
{
  "summary": "整体情况摘要",
  "metrics": {
    "taskCount": 0,
    "completedTaskCount": 0,
    "unfinishedTaskCount": 0,
    "overdueTaskCount": 0,
    "scheduledHours": 0,
    "completedHours": 0,
    "overdueHours": 0
  },
  "risks": [],
  "suggestions": [],
  "evidence": []
}
```

字段说明：

- `summary`：给用户看的总览结论。
- `metrics`：结构化数字指标，前端可以直接展示。
- `risks`：风险列表。
- `suggestions`：建议动作列表。
- `evidence`：支撑分析的关键数据点。
