# 绩效数据库设计文档

## 1. 数据库架构

绩效数据使用独立 SQLite 数据库 `perf.db`，与主业务库 `main.db` 物理分离。

```
backend/data/
├── main.db      ← 主业务库（用户角色、项目任务、同步记录）
└── perf.db      ← 绩效专用库
```

perf.db 通过环境变量 `PERF_DATABASE_URI` 可切换为 MySQL。

---

## 2. 表结构

### 2.1 两张表，按团队分

结构完全相同，写入时通过 UserCharacter.team_id 路由，查询时两张表就是两个团队：

| 表名 | 团队 |
|:--|:--|
| `nav_perf_quarter_result` | 导航组 |
| `servo_perf_quarter_result` | 对接组 |

### 2.2 设计原则

- **一行自包含完整计算链**：无需翻其他行就能看懂输入 → 计算 → 判断 → 结论。
- **身份字段存快照，不实时关联**：`is_team_lead` 落库为当时的值，避免人员变动导致历史季度公式错乱。
- **不存可推导的冗余列**：能通过本行数据算出来的不存，能 join 查到的展示字段不存。

---

## 2.3 字段清单（21 列）

一行 = 一个人 × 一个季度。唯一约束：`(year, quarter, user_id)`。

### 标识层（10 列）

| 字段 | 类型 | 必填 | 说明 |
|:--|:--|:--|:--|
| `id` | INTEGER PK | ✓ | 自增主键 |
| `year` | INTEGER | ✓ | 年份 |
| `quarter` | INTEGER | ✓ | 季度 1/2/3/4 |
| `user_id` | VARCHAR(64) | ✓ | 用户 ID |
| `is_team_lead` | BOOLEAN | ✓ | **快照**。TRUE=组长，FALSE=成员。决定用哪个公式，必须落库为计算当时的值 |
| `rule_code` | VARCHAR(64) | ✓ | 公式版本编码，如 `quarter_perf_v2025q1_mgr_no_okr` |
| `calc_status` | VARCHAR(32) | ✓ | `filled` → `calculated` |
| `created_at` | DATETIME | ✓ | 创建时间 |
| `updated_at` | DATETIME | ✓ | 更新时间 |

### 输入层（2 列）

| 字段 | 角色 | 类型 | 含义 | 来源 |
|:--|:--|:--|:--|:--|
| `work_hour_score` | 📥 输入 | FLOAT | TB 工时绩效 | TB 系统统计，范围 0~2 |
| `supervisor_score` | 📥 输入 | FLOAT | 主管评分 | 主管手工评定：0 / 0.5 / 0.8 / 1.0 / 1.2 / 1.5 / 2.0 |

### 计算层（9 列）

一行内的完整计算视图：

```
 supervisor_score ────┐
 work_hour_score ─────┤    ┌─── 输入层
                      ▼    │
                 overall_score  ← 第一步
                      │    │
       ┌──────────────┴──────────────┐
       ▼                              ▼
compensation_value            overflow_value    ┌─── 判断量
       │                              │         │
       │    prev_carry_balance        │         │
       │    prev_decay_value          │         │
       └──────────┬───────────────────┘         │
                  ▼                             │
             final_score                        │
                  │                             │
    ┌─────────────┼─────────────┐              │
    ▼             ▼             ▼              │
new_carry    carry_decay    company_score       └─── 结论
_balance       _value
    │             │
    └──────┬──────┘
           ▼
      传给下季度
```

| # | 字段 | 角色 | 类型 | 含义 | 公式 / 来源 |
|:--|:--|:--|:--|:--|:--|
| 1 | `overall_score` | 🔧 计算 | FLOAT | 总体绩效 | `ROUND(工时×0.7 + 主管×0.3, 3)` |
| 2 | `prev_carry_balance` | 📤 上季 | FLOAT | 上季结余余额 | = 上季度 `new_carry_balance`，计算时查询写入本行 |
| 3 | `prev_decay_value` | 📤 上季 | FLOAT | 上季衰减值 | = 上季度 `carry_decay_value`，计算时查询写入本行 |
| 4 | `compensation_value` | 🔧 判断 | FLOAT | 补偿值 | `overall − threshold_upper`，负数=离下一档还差多少 |
| 5 | `overflow_value` | 🔧 判断 | FLOAT | 溢出值 | `overall − threshold_lower`，当前档内超出多少 |
| 6 | `final_score` | 🏁 结论 | FLOAT | 最终绩效系数 | `prev_carry + compensation >= 0 ? upper : lower` |
| 7 | `new_carry_balance` | 🔄 状态 | FLOAT | 本季新结余 | 升档: `max(prev+comp−decay, 0)`；未升档: `prev×0.75+overflow` |
| 8 | `carry_decay_value` | 🔄 状态 | FLOAT | 本季衰减值 | `ROUND(new_carry × 0.25, 3)` |
| 9 | `company_score` | 🏁 结论 | FLOAT | 公司绩效 | `final_score` 查档位映射表 |

---

### 2.4 字段速查

```
┌───────────────────────────┬──────────────────────────┐
│ 标识（10）                  │ 输入（2）                 │
├───────────────────────────┼──────────────────────────┤
│ id, year, quarter         │ work_hour_score   ★TB   │
│ user_id                   │ supervisor_score  ★主管  │
│ is_team_lead   ★快照      │                          │
│ rule_code                 ├──────────────────────────┤
│ calc_status               │ 计算（9）                 │
│ created_at, updated_at    ├──────────────────────────┤
│                           │ overall_score            │
│                           │ prev_carry_balance       │
│                           │ prev_decay_value         │
│                           │ compensation_value       │
│                           │ overflow_value           │
│                           │ final_score      ★定档   │
│                           │ new_carry_balance        │
│                           │ carry_decay_value        │
│                           │ company_score    ★挂钱   │
└───────────────────────────┴──────────────────────────┘
```

---

### 2.5 不在表中的列

| 不入库的列 | 获取方式 |
|:--|:--|
| `user_name` | `JOIN main_db.user_character ON user_id` |
| `team_id` / `team_name` | 所在表即团队（nav / servo） |
| `role_type` | `is_team_lead ? "manager" : "employee"` |
| `threshold_lower` | 未升档: `= final_score`；升档: 查档位表 |
| `threshold_upper` | `overall_score` 查档位表 |
| `carry_score` | `= overall_score + prev_carry_balance`，本行相加 |
| `carry_calc_mode` | `= prev_carry + compensation >= 0 ? "upgrade_then_decay" : "decay_then_add_overflow"` |
| `calc_trace_json` | 本行数字已完整，无需冗余 JSON |
| `okr_score` | 组长旧版公式（未实现） |
| `team_avg_score` | 聚合值，不应存个人行 |

---

## 3. 数据流

```
主管填 supervisor_score ─┐
TB 系统出 work_hour_score ─┤
                          ▼
                   ┌─────────────┐
                   │  fill 接口   │  写入输入列，calc_status = "filled"
                   │             │  同时从 UserCharacter 读取 is_team_lead 快照
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ calculate   │  1. 查上季度 new_carry / carry_decay
                   │  计算全链    │     → 写入 prev_carry_balance / prev_decay_value
                   │             │  2. 根据 is_team_lead + rule_code 选公式
                   │             │  3. 计算 overall_score
                   │             │  4. 查档位 → 算 compensation / overflow
                   │             │  5. 判断升档 → final_score
                   │             │  6. 算 new_carry / carry_decay / company_score
                   │             │  7. calc_status = "calculated"
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │  query 接口  │  返回整行 + JOIN 展示字段（user_name 等）
                   └─────────────┘
```

---

## 4. 与 UserCharacter 的关系

perf.db 通过 `user_id` 关联 main.db 的 `user_character`。

### fill 时读取（写入快照）

| UserCharacter 字段 | 用途 |
|:--|:--|
| `team_id` | 决定写入 nav 还是 servo 表 |
| `character` | `0` → `is_team_lead=TRUE`，其他 → `is_team_lead=FALSE`。**落库为快照，后续 UserCharacter 变更不影响历史行** |

### query 时 JOIN（获取展示字段）

```sql
SELECT p.*, uc.name AS user_name
FROM nav_perf_quarter_result p
JOIN main.user_character uc ON p.user_id = uc.user_id
WHERE p.year = 2025 AND p.quarter = 2;
```

**必须先注册 user_character，再操作 perf.db。**

---

## 5. SQL 示例

```sql
-- 查某季度所有人结果（JOIN 获取 user_name）
SELECT uc.name AS user_name,
       p.work_hour_score, p.supervisor_score,
       p.overall_score,
       p.prev_carry_balance, p.prev_decay_value,
       p.compensation_value, p.overflow_value,
       p.final_score,
       p.new_carry_balance, p.carry_decay_value,
       p.company_score
FROM nav_perf_quarter_result p
JOIN main.user_character uc ON p.user_id = uc.user_id
WHERE p.year = 2025 AND p.quarter = 2;

-- 查某人历史
SELECT year, quarter, final_score, new_carry_balance, company_score
FROM nav_perf_quarter_result
WHERE user_id = 'zhangsan'
ORDER BY year, quarter;

-- 验证跨季度结余传递
SELECT year, quarter,
       prev_carry_balance, new_carry_balance,
       prev_decay_value, carry_decay_value
FROM nav_perf_quarter_result
WHERE user_id = 'zhangsan'
ORDER BY year, quarter;
```

---

## 6. 接口

| 方法 | 路径 | 作用 |
|:--|:--|:--|
| POST | `/api/bt/perf/fill-quarter-member` | 写入输入，快照 is_team_lead，status → `filled` |
| POST | `/api/bt/perf/calculate-quarter-member` | 执行计算，status → `calculated` |
| GET | `/api/bt/perf/query?year=&quarter=&userId=` | 查询结果（JOIN user_name） |

---

## 7. 注意

1. **按季度顺序计算**：每季度依赖上季度的 `new_carry_balance` 和 `carry_decay_value`。
2. **填充后才能计算**：`calc_status` 必须为 `filled`。
3. **重算需级联**：改历史季度 → 后续所有季度都得重算。
4. **小数精度**：统一 3 位 + HALF_UP，每步单独 round。
5. **一行自包含**：`prev_carry_balance` / `prev_decay_value` 在计算时从上季度查来写入本行，查询时无需跨行。
6. **is_team_lead 是快照**：fill 时从 UserCharacter 读取并落库，后续 UserCharacter 变更不影响已入库的历史行。
