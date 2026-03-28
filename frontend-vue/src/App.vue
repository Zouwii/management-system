<script setup>
import { countWorkdays } from "chinese-workday";
import { ElMessage } from "element-plus";
import { computed, onMounted, ref, watch } from "vue";
import { API_BASE, WORKHOUR_FIELD_ID } from "./config.js";

function _toFloat(x) {
  if (x == null) return null;
  if (typeof x === "number" && Number.isFinite(x)) return x;
  if (typeof x === "string") {
    const m = x.match(/-?\d+(\.\d+)?/);
    if (m) return parseFloat(m[0]);
    const n = parseFloat(x);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** 与后端 workhour_util.parse_value_to_float 对齐 */
function parseValueToFloat(vals) {
  if (vals == null) return null;
  if (typeof vals === "string") {
    try {
      vals = JSON.parse(vals);
    } catch {
      vals = [];
    }
  }
  if (Array.isArray(vals) && vals.length > 0) {
    const v0 = vals[0];
    const obj = typeof v0 === "object" && v0 ? v0 : {};
    const x = obj.title ?? obj.value ?? obj.numberValue;
    return _toFloat(x);
  }
  if (typeof vals === "object" && vals !== null && !Array.isArray(vals)) {
    const x = vals.title ?? vals.value;
    return _toFloat(x);
  }
  return _toFloat(vals);
}

function parseWorkhourFromTaskDict(task, targetFieldId) {
  const fields = task?.customFields ?? task?.customfields;
  if (!Array.isArray(fields)) return null;
  const tid = String(targetFieldId);
  for (const f of fields) {
    if (!f || typeof f !== "object") continue;
    const fid = f.customFieldId ?? f.customfieldId;
    if (String(fid ?? "") !== tid) continue;
    return parseValueToFloat(f.value);
  }
  return null;
}

function taskItemsFromDingtalk(ding) {
  const raw = ding?.result;
  if (Array.isArray(raw)) return raw.filter((x) => x && typeof x === "object");
  if (raw && typeof raw === "object") return [raw];
  return [];
}

function sumOrderWorkhoursFromApiData(data) {
  const inner = (data || {}).data;
  const ding = inner?.data?.dingtalk;
  if (!ding || typeof ding !== "object") return 0;
  const items = taskItemsFromDingtalk(ding);
  let sum = 0;
  for (const t of items) {
    const w = parseWorkhourFromTaskDict(t, WORKHOUR_FIELD_ID);
    if (w != null && Number.isFinite(w)) sum += w;
  }
  return Math.round(sum * 100) / 100;
}

// 软件开发（按你之前的过滤逻辑）
const DEV_SCENARIO_ID = "647854bcd999c893061ef8b5";

const users = ref([]); // [{name,userId}]
const projects = ref([]); // [{name,projectId}]

// 左侧：项目任务查询
const projectUserId = ref("");
const projectId = ref("");
const dueDateStart = ref("2026-01-01T00:00:00");
const dueDateEnd = ref("2026-03-31T23:59:59");
const projectOut = ref("请先查询项目任务");
const projectMetaHint = ref("等待查询…");
const projectLoading = ref(false);

/** 年假/事假等占用工作日天数，用于从法定工作日中扣减 */
const leaveDays = ref(0);

/** 根据开始/结束日期（取日期部分）统计法定工作日，含调休补班 */
const statutoryWorkdaySummary = computed(() => {
  const s = (dueDateStart.value || "").trim();
  const e = (dueDateEnd.value || "").trim();
  if (!s || !e) {
    return {
      state: "pending",
      text: "选择开始时间、结束时间后，将显示区间内法定工作日天数（含调休补班）。",
    };
  }
  const ds = s.slice(0, 10);
  const de = e.slice(0, 10);
  const t0 = new Date(`${ds}T12:00:00`).getTime();
  const t1 = new Date(`${de}T12:00:00`).getTime();
  if (Number.isNaN(t0) || Number.isNaN(t1)) {
    return { state: "error", text: "日期无效，请重新选择。" };
  }
  if (t1 < t0) {
    return { state: "error", text: "结束日期不能早于开始日期。" };
  }
  try {
    const n = countWorkdays(ds, de);
    return {
      state: "ok",
      text: `${ds} 至 ${de}，共 ${n} 天法定工作日（按国务院放假安排，含调休）。`,
      n,
    };
  } catch {
    return {
      state: "error",
      text: "无法计算（日期可能超出节假日数据范围，约 2011–2026 年）。",
    };
  }
});

const leaveDaysEffective = computed(() => {
  const v = Number(leaveDays.value);
  if (!Number.isFinite(v) || v < 0) return 0;
  return v;
});

/** 法定工作日 − 请假天数（不为负） */
const netWorkdaysTotal = computed(() => {
  const s = statutoryWorkdaySummary.value;
  if (s.state !== "ok" || typeof s.n !== "number") return null;
  return Math.max(0, s.n - leaveDaysEffective.value);
});

/** 所需工时 = 工作日总数 × 比例（70% / 80%） */
const workHoursPercent = ref(80);

const requiredWorkHours = computed(() => {
  const days = netWorkdaysTotal.value;
  if (days === null) return null;
  const p = Number(workHoursPercent.value);
  const pct = p === 70 || p === 80 ? p : 80;
  const v = days * (pct / 100);
  return Math.round(v * 100) / 100;
});

// 右侧：任务详情查询
const taskUserId = ref("");
const taskExecutorId = ref("");
const selectedTaskId = ref("");
const taskOut = ref("等待查询任务...");
const taskLoading = ref(false);
const aggregateLoading = ref(false);
/** 服务端「工时统计」一次请求返回的汇总 */
const executorAggregateTotal = ref(null);

/** 最近一次「查询任务详情」从接口汇总得到的任务工时；成功查询后更新 */
const taskDetailOrderWorkHours = ref(null);
/** 季度预期（工时）；业务未接前固定 0，后续可绑接口 */
const quarterExpectedHours = ref(0);

const totalWorkhoursBarState = computed(() =>
  taskDetailOrderWorkHours.value == null ? "pending" : "ok",
);

const totalWorkhoursSum = computed(() => {
  if (taskDetailOrderWorkHours.value == null) return null;
  const o = Number(taskDetailOrderWorkHours.value);
  const q = Number(quarterExpectedHours.value);
  const qv = Number.isFinite(q) && q >= 0 ? q : 0;
  if (!Number.isFinite(o)) return qv;
  return Math.round((o + qv) * 100) / 100;
});

// 来自左侧的结果（用于右侧下拉）
const allTaskOptions = ref([]); // [{id,name,executorId}]

/** 项目名以「本体开发部」开头时，下拉只显示该四字，去掉后面多余字符 */
function projectSelectLabel(name) {
  const n = String(name ?? "").trim();
  const prefix = "本体开发部";
  if (n.startsWith(prefix)) return prefix;
  return n;
}

function joinUrl(base, path) {
  const b = (base || "").replace(/\/+$/, "");
  const p = String(path || "").startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

async function apiFetch(path, init) {
  const url = joinUrl(API_BASE, path);
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data && data.error ? data.error : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function prettyJsonWithLimit(obj, maxLen = 20000) {
  const s = JSON.stringify(obj, null, 2);
  if (s.length <= maxLen) return s;
  return `${s.slice(0, maxLen)}\n...（结果过大，已截断显示，总长度 ${s.length}）`;
}

function toIsoFromDatetimeLocal(v) {
  return new Date(v).toISOString();
}

function forceStartDayTime() {
  const v = (dueDateStart.value || "").trim();
  if (!v) return;
  const d = v.slice(0, 10);
  if (!d) return;
  dueDateStart.value = `${d}T00:00:00`;
}

function forceEndDayTime() {
  const v = (dueDateEnd.value || "").trim();
  if (!v) return;
  const d = v.slice(0, 10);
  if (!d) return;
  dueDateEnd.value = `${d}T23:59:59`;
}

function buildProjectQuery() {
  const clauses = [];
  const start = (dueDateStart.value || "").trim();
  const end = (dueDateEnd.value || "").trim();
  if (start) clauses.push(`dueDate >= '${toIsoFromDatetimeLocal(start)}'`);
  if (end) clauses.push(`dueDate <= '${toIsoFromDatetimeLocal(end)}'`);
  if (clauses.length === 0) return "";
  return clauses.map((c) => `(${c})`).join(" AND ");
}

function filterSoftwareOnly(resp) {
  const cloned = JSON.parse(JSON.stringify(resp || {}));
  const dingtalk = ((((cloned || {}).data || {}).data || {}).dingtalk) || {};
  if (!Array.isArray(dingtalk.result)) return cloned;
  dingtalk.result = dingtalk.result.filter((x) => {
    const sid = (x && (x.scenarioFieldConfigId || x.scenariofieldconfigId)) || "";
    return sid === DEV_SCENARIO_ID;
  });
  return cloned;
}

function fillTaskOptionsFromProjectResult(resp) {
  const dingtalk = ((((resp || {}).data || {}).data || {}).dingtalk) || {};
  if (!Array.isArray(dingtalk.result)) {
    allTaskOptions.value = [];
    selectedTaskId.value = "";
    return;
  }
  const out = dingtalk.result
    .map((x) => ({
      id: x && x.taskId ? String(x.taskId) : "",
      name: x && x.content ? String(x.content) : "",
      executorId: x && x.executorId ? String(x.executorId) : "",
    }))
    .filter((x) => x.id);

  const dedup = {};
  out.forEach((x) => {
    if (!dedup[x.id]) dedup[x.id] = x;
  });
  allTaskOptions.value = Object.keys(dedup).map((k) => dedup[k]);
}

/** 仅按执行者缩小候选；关键词在任务下拉里用 filterable 按选项文案筛选 */
const filteredTaskOptions = computed(() => {
  const ex = (taskExecutorId.value || "").trim();
  let items = allTaskOptions.value || [];
  if (ex) items = items.filter((x) => (x.executorId || "") === ex);
  return items;
});

const taskOptionHint = computed(() => `任务候选：${filteredTaskOptions.value.length}`);

/** 下拉仅展示标题时，用自定义筛选仍可按标题或 taskId 过滤 */
const taskSelectQuery = ref("");
const displayedTaskOptions = computed(() => {
  const items = filteredTaskOptions.value || [];
  const q = (taskSelectQuery.value || "").trim();
  if (!q) return items;
  return items.filter(
    (x) =>
      String(x.name || "").includes(q) || String(x.id || "").includes(q),
  );
});

function onTaskSelectFilter(query) {
  taskSelectQuery.value = query ?? "";
}

/** 左侧列表中的 taskId → 中文标题（与下拉一致） */
function buildTaskIdTitleMap() {
  const m = Object.create(null);
  for (const t of allTaskOptions.value || []) {
    if (t && t.id) m[String(t.id)] = String(t.name || "").trim();
  }
  return m;
}

watch(filteredTaskOptions, (opts) => {
  taskSelectQuery.value = "";
  if (!opts || opts.length === 0) {
    selectedTaskId.value = "";
    return;
  }
  if (!selectedTaskId.value || !opts.some((x) => x.id === selectedTaskId.value)) {
    selectedTaskId.value = opts[0].id;
  }
});

function showErr(setter, err) {
  const msg = err && err.message ? err.message : String(err);
  setter(`错误：${msg}\n（后端地址：${API_BASE}）`);
}

async function reloadConfigOptions() {
  const [u, p] = await Promise.all([
    apiFetch("/api/bt/config/userids"),
    apiFetch("/api/bt/config/projectids"),
  ]);
  users.value = (((u || {}).data || {}).users) || [];
  projects.value = (((p || {}).data || {}).projects) || [];

  const DEFAULT_USER_NAME = "邹宏睿";
  const zhr = (users.value || []).find((x) => String(x && x.name) === DEFAULT_USER_NAME);
  const firstUserId = zhr?.userId || users.value?.[0]?.userId || "";

  if (!projectUserId.value) projectUserId.value = firstUserId;
  if (!taskUserId.value) taskUserId.value = firstUserId;
  if (!taskExecutorId.value) taskExecutorId.value = firstUserId;
  if (!projectId.value) projectId.value = projects.value?.[0]?.projectId || "";
}

async function doProjectQuery() {
  projectLoading.value = true;
  try {
    projectOut.value = "查询项目任务中...";
    projectMetaHint.value = "请求中…";

    const payload = {
      userId: (projectUserId.value || "").trim(),
      projectId: (projectId.value || "").trim(),
      query: buildProjectQuery(),
      maxResults: 500,
    };
    if (!payload.userId || !payload.projectId) {
      projectOut.value = "请先选择操作者和项目。";
      projectMetaHint.value = "缺少必填字段";
      return;
    }

    const data = await apiFetch("/api/bt/query_project_tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const softwareOnlyData = filterSoftwareOnly(data);
    projectOut.value = "已完成项目任务查询";

    const dingtalk = ((((softwareOnlyData || {}).data || {}).data || {}).dingtalk) || {};
    const total = Array.isArray(dingtalk.result) ? dingtalk.result.length : 0;
    projectMetaHint.value = `已加载（软件开发过滤后）：${total} 条`;

    setTimeout(() => fillTaskOptionsFromProjectResult(softwareOnlyData), 0);
  } catch (e) {
    showErr((t) => (projectOut.value = t), e);
    projectMetaHint.value = "失败";
  } finally {
    projectLoading.value = false;
  }
}

async function doTaskQuery() {
  taskLoading.value = true;
  try {
    executorAggregateTotal.value = null;
    taskOut.value = "查询任务中...";
    const payload = {
      userId: (taskUserId.value || "").trim(),
      taskId: (selectedTaskId.value || "").trim(),
    };
    if (!payload.userId || !payload.taskId) {
      taskOut.value = "请先在左侧查询项目任务后，选择任务。";
      return;
    }
    const data = await apiFetch("/api/bt/query_task_details", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    taskDetailOrderWorkHours.value = sumOrderWorkhoursFromApiData(data);
    taskOut.value = prettyJsonWithLimit(data);
  } catch (e) {
    taskDetailOrderWorkHours.value = null;
    showErr((t) => (taskOut.value = t), e);
  } finally {
    taskLoading.value = false;
  }
}

/** 将工时统计 breakdown 格式化为「中文名 + 工时」两列表格文本（标题与左侧列表一致） */
function formatExecutorWorkhoursText(d, idToTitle) {
  const map = idToTitle && typeof idToTitle === "object" ? idToTitle : {};
  const rows = Array.isArray(d?.breakdown) ? d.breakdown : [];
  const lines = ["中文名\t工时"];
  for (const row of rows) {
    const tid = String(row?.taskId || "").trim();
    const fromApi = String(row?.content || "").trim();
    const fromList = tid ? String(map[tid] || "").trim() : "";
    const name = fromApi || fromList || tid;
    const h = row?.work_hour;
    const hStr =
      h != null && typeof h === "number" && Number.isFinite(h) ? String(h) : "—";
    lines.push(`${name}\t${hStr}`);
  }
  const total = d?.total_work_hour;
  if (typeof total === "number" && Number.isFinite(total)) {
    lines.push(`合计\t${total}`);
  }
  return lines.join("\n");
}

/** 单次 POST：服务端按执行者循环拉详情并汇总工时（F12 仅一条请求） */
async function doExecutorWorkhoursStats() {
  aggregateLoading.value = true;
  try {
    executorAggregateTotal.value = null;
    const uid = (taskUserId.value || "").trim();
    const pid = (projectId.value || "").trim();
    const ex = (taskExecutorId.value || "").trim();
    if (!uid || !pid) {
      ElMessage.warning("请选择右侧「操作者」与左侧「项目」。");
      return;
    }
    if (!ex) {
      ElMessage.warning("请选择「执行者（筛选下拉）」，将只统计该执行者的任务。");
      return;
    }
    const body = {
      userId: uid,
      projectId: pid,
      executorId: ex,
      query: buildProjectQuery(),
      maxResults: 500,
      workHourFieldId: WORKHOUR_FIELD_ID,
    };
    const res = await apiFetch("/api/bt/stats/executor_workhours", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = (res && res.data) || {};
    const total = d.total_work_hour;
    executorAggregateTotal.value =
      typeof total === "number" && Number.isFinite(total) ? total : null;
    taskOut.value = formatExecutorWorkhoursText(d, buildTaskIdTitleMap());
    ElMessage.success(`工时合计：${executorAggregateTotal.value ?? "—"}`);
  } catch (e) {
    executorAggregateTotal.value = null;
    showErr((t) => (taskOut.value = t), e);
  } finally {
    aggregateLoading.value = false;
  }
}

onMounted(async () => {
  try {
    await reloadConfigOptions();
    projectOut.value = "请先查询项目任务";
    taskOut.value = "就绪（请先查询左侧）。";
  } catch (e) {
    showErr((t) => (projectOut.value = t), e);
    showErr((t) => (taskOut.value = t), e);
  }
});
</script>

<template>
  <div class="page">
    <div class="header">
      <h1>本体开发部</h1>
    </div>

    <div class="main">
      <div class="split">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
              <div>
                <div style="font-weight:700">项目任务查询</div>
                <div style="font-size:12px;color:#606266;margin-top:4px">
                  <span class="mono">POST /api/bt/query_project_tasks</span>
                </div>
              </div>
              <el-tag type="warning" effect="light">{{ projectMetaHint }}</el-tag>
            </div>
          </template>

          <div
            class="statutory-workday-bar"
            :data-state="statutoryWorkdaySummary.state"
          >
            <div class="statutory-workday-bar__main">
              <span class="statutory-workday-bar__text">{{
                statutoryWorkdaySummary.text
              }}</span>
              <span class="statutory-workday-bar__leave-wrap">
                <span class="statutory-workday-bar__leave-label">年假/事假（天）</span>
                <el-input-number
                  v-model="leaveDays"
                  :min="0"
                  :precision="1"
                  :step="0.5"
                  size="small"
                  controls-position="right"
                  class="statutory-workday-bar__leave-input"
                />
              </span>
            </div>
            <div
              v-if="
                statutoryWorkdaySummary.state === 'ok' &&
                netWorkdaysTotal !== null &&
                requiredWorkHours !== null
              "
              class="statutory-workday-bar__result"
            >
              <div class="statutory-workday-bar__result-row">
                <span class="statutory-workday-bar__result-days">
                  工作日总数：<strong>{{ netWorkdaysTotal }}</strong> 天
                  <span class="statutory-workday-bar__formula">
                    （法定工作日 {{ statutoryWorkdaySummary.n }} − 请假
                    {{ leaveDaysEffective }}）
                  </span>
                </span>
                <span class="statutory-workday-bar__result-hours">
                  <span class="statutory-workday-bar__times" aria-hidden="true">×</span>
                  <el-select
                    v-model="workHoursPercent"
                    size="small"
                    class="statutory-workday-bar__pct-select"
                  >
                    <el-option :value="70" label="70%" />
                    <el-option :value="80" label="80%" />
                  </el-select>
                  <span class="statutory-workday-bar__hours-label">
                    所需工时数：<strong>{{ requiredWorkHours }}</strong>
                  </span>
                  <span class="statutory-workday-bar__formula">
                    （{{ netWorkdaysTotal }} 天 × {{ workHoursPercent }}%）
                  </span>
                </span>
              </div>
            </div>
          </div>

          <el-form label-position="top">
            <el-row :gutter="12">
              <el-col :xs="24" :md="12">
                <el-form-item label="操作者（必填）">
                  <el-select v-model="projectUserId" filterable placeholder="请选择操作者" style="width:100%">
                    <el-option
                      v-for="u in users"
                      :key="u.userId"
                      :label="u.name"
                      :value="u.userId"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="项目（必填）">
                  <el-select v-model="projectId" filterable placeholder="请选择项目" style="width:100%">
                    <el-option
                      v-for="p in projects"
                      :key="p.projectId"
                      :label="projectSelectLabel(p.name)"
                      :value="p.projectId"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :xs="24" :md="12">
                <el-form-item label="开始时间（时分秒）">
                  <el-input v-model="dueDateStart" type="datetime-local" @change="forceStartDayTime" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="结束时间（时分秒）">
                  <el-input v-model="dueDateEnd" type="datetime-local" @change="forceEndDayTime" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <el-button type="warning" :loading="projectLoading" @click="doProjectQuery">
                查询项目任务
              </el-button>
              <el-text type="info" style="margin-left: 10px">
                点击按钮查询本体开发部
              </el-text>
            </el-form-item>
          </el-form>

          <div class="out">{{ projectOut }}</div>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
              <div>
                <div style="font-weight:700">任务工时统计</div>
                <div style="font-size:12px;color:#606266;margin-top:4px">
                  <span class="mono">POST /api/bt/query_task_details</span>
                  ·
                  <span class="mono">POST /api/bt/stats/executor_workhours</span>
                </div>
              </div>
              <el-tag type="info" effect="light">{{ taskOptionHint }}</el-tag>
            </div>
          </template>

          <div
            v-if="executorAggregateTotal !== null"
            class="statutory-workday-bar total-workhours-bar"
            data-state="ok"
            style="margin-bottom:12px"
          >
            <div>
              <strong>执行者工时汇总</strong>（单次服务端请求）：合计
              <strong>{{ executorAggregateTotal }}</strong>
              <span class="statutory-workday-bar__formula">（明细见下方，仅任务名与工时）</span>
            </div>
          </div>

          <div
            class="statutory-workday-bar total-workhours-bar"
            :data-state="totalWorkhoursBarState"
          >
            <template v-if="totalWorkhoursBarState === 'pending'">
              点击「查询任务详情」可查看单条 JSON；单条任务的工时与下方「季度预期」相加为
              <span class="mono">总工时</span>。季度预期业务待接入，当前按 0 计。
            </template>
            <template v-else>
              <div>
                总工时（单条） =
                <strong>{{ totalWorkhoursSum }}</strong>
                <span class="statutory-workday-bar__formula">
                  （当前任务工时 {{ taskDetailOrderWorkHours }} + 季度预期
                  {{ quarterExpectedHours }}）
                </span>
              </div>
            </template>
          </div>

          <el-form label-position="top">
            <el-row :gutter="12">
              <el-col :xs="24" :md="12">
                <el-form-item label="操作者（必填）">
                  <el-select v-model="taskUserId" filterable placeholder="请选择操作者" style="width:100%">
                    <el-option
                      v-for="u in users"
                      :key="u.userId"
                      :label="u.name"
                      :value="u.userId"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="执行者（筛选下拉）">
                  <el-select v-model="taskExecutorId" clearable filterable placeholder="全部" style="width:100%">
                    <el-option
                      v-for="u in users"
                      :key="u.userId"
                      :label="u.name"
                      :value="u.userId"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="任务（来自左侧；可在此框内输入关键词或任务 ID 筛选）">
              <el-select
                v-model="selectedTaskId"
                filterable
                :filter-method="onTaskSelectFilter"
                placeholder="请先在左侧查询项目任务，在此输入筛选"
                style="width:100%"
              >
                <el-option
                  v-for="t in displayedTaskOptions"
                  :key="t.id"
                  :label="t.name"
                  :value="t.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item>
              <el-button type="warning" :loading="taskLoading" @click="doTaskQuery">
                查询任务详情
              </el-button>
              <el-button
                type="primary"
                :loading="aggregateLoading"
                style="margin-left: 8px"
                @click="doExecutorWorkhoursStats"
              >
                工时统计
              </el-button>
              <el-text type="info" style="margin-left: 10px; font-size: 12px">
                「工时统计」由后端循环拉详情，浏览器只发 1 次请求
              </el-text>
            </el-form-item>

            <el-alert
              title="提示"
              type="info"
              :closable="false"
              show-icon
              description="下拉来自左侧列表；单条点「查询任务详情」。按执行者汇总点「工时统计」（须选执行者，与左侧同一项目+时间条件）。"
            />
          </el-form>

          <div class="out">{{ taskOut }}</div>
        </el-card>
      </div>
    </div>
  </div>
</template>

