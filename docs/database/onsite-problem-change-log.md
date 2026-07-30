# onsite_problem 变更记录

## 2026-07-24: B 表切换至 TB Open API via proxy（含评论 + 附件）

### 数据来源切换

| 表 | 旧来源 | 新来源 |
|----|--------|--------|
| A 表 | 钉钉项目 API | **不变** |
| B 表 | 钉钉项目 API (逐条详情) | **TB Open API via proxy** |

A 表时间限定：**已取消**，全量拉取。

### B 表新增列

| 列名 | 类型 | 说明 |
|------|------|------|
| `comments_json` | MEDIUMTEXT | 评论流 JSON，按时间正序，含 `attachment_indices` |
| `attachments_json` | MEDIUMTEXT | 附件流 JSON，含 fileName/fileSize/mimeType/resourceId |

### 新增文件

| 文件 | 作用 |
|------|------|
| `backend/base/onsite_problem/tb_proxy.py` | TB Open API 代理封装 + 凭据管理 |

API 调用（通过 `http://claude.server22.jz/api/dingtalk/proxy` 中转）：
- `GET /api/v3/task/query?taskId=xxx`
- `GET /api/v3/task/{id}/activity/list?pageSize=50`
- `POST /api/v3/file/query/by-resource-ids`

### 新增路由

| 路由 | 方法 | 用途 |
|------|------|------|
| `/onsite/check-proxy` | GET | 检查代理凭据是否有效 |
| `/onsite/update-proxy` | POST | 更新凭据 + 自动验证 |

### 凭据过期流程

```
/check-proxy → 401/403
  → "凭据已过期。请通过诊断终端 (diagkit) 获取新的 proxyToken/unionId，
     然后 POST /onsite/update-proxy 更新"
  → curl .../onsite/update-proxy -d '{"proxyToken":"...","unionId":"..."}'
  → 自动验证 → 完成
```

### 修改文件

| 文件 | 改动 |
|------|------|
| `backend/.env` | 新增 DINGTALK_PROXY_TOKEN / DINGTALK_UNION_ID |
| `backend/base/onsite_problem/tb_proxy.py` | 新建 |
| `backend/base/onsite_problem/sync.py` | B 表改 proxy，加凭据预检 |
| `backend/base/onsite_problem/routes.py` | 新增 check-proxy / update-proxy |
| `backend/base/db/orm.py` | OnsiteProblemDetail 加 comments_json / attachments_json |
