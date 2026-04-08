<script setup>
import { countWorkdays } from "chinese-workday";
import { ElMessage } from "element-plus";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Setting } from "@element-plus/icons-vue";
import {
  API_BASE,
  WORKHOUR_COEFFICIENT,
  WORKHOUR_FIELD_ID,
} from "./config.js";

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

function showErr(setter, err) {
  const msg = err && err.message ? err.message : String(err);
  setter(`错误：${msg}\n（后端地址：${API_BASE}）`);
}

function toIsoFromDatetimeLocal(v) {
  // `datetime-local` 的字符串不带时区，被浏览器当成本地时间解析；
  // 这里我们希望把它当作 UTC 时间来处理，避免在 UTC+8 下显示/计算偏移。
  let s = String(v || "");
  if (!s) return "";
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s)) s = `${s}:00`;
  if (!s.endsWith("Z")) s = `${s}Z`;
  return new Date(s).toISOString();
}

function toIsoForQueryStart(v) {
  const d = new Date(toIsoFromDatetimeLocal(v));
  if (Number.isNaN(d.getTime())) return toIsoFromDatetimeLocal(v);
  d.setMilliseconds(0);
  return d.toISOString();
}

function toIsoForQueryEnd(v) {
  const d = new Date(toIsoFromDatetimeLocal(v));
  if (Number.isNaN(d.getTime())) return toIsoFromDatetimeLocal(v);
  d.setMilliseconds(999);
  return d.toISOString();
}

// 用于后端查询范围的默认日期区间（不在新页面里展示，但仍用于：
// 1) 计算法定节假日/调休相关天数（用国务院放假安排）
// 2) 过滤后端任务查询范围）
const dueDateStart = ref("2026-01-01T00:00:00");
const dueDateEnd = ref("2026-03-31T23:59:59");
const lastUpdateTime = ref("");

// 设置子界面（弹窗）
const showSettings = ref(false);
const settingsDueDateStart = ref("");
const settingsDueDateEnd = ref("");
const autoCalcEnabled = ref(false);
const autoCalcTime = ref("09:00");
const settingsAutoCalcEnabled = ref(false);
const settingsAutoCalcTime = ref("09:00");

function isoToDatetimeLocal(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  // 展示用 UTC 字段，避免 UTC+8 本地时区导致看起来“+8小时”
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(
    d.getUTCMinutes(),
  )}:${pad(d.getUTCSeconds())}`;
}

function formatLastUpdateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

const lastUpdateTimeDisplay = computed(() => formatLastUpdateTime(lastUpdateTime.value));

function buildProjectQuery() {
  const clauses = [];
  const start = (dueDateStart.value || "").trim();
  const end = (dueDateEnd.value || "").trim();
  if (start) clauses.push(`dueDate >= '${toIsoForQueryStart(start)}'`);
  if (end) clauses.push(`dueDate <= '${toIsoForQueryEnd(end)}'`);
  if (clauses.length === 0) return "";
  return clauses.map((c) => `(${c})`).join(" AND ");
}

// 基础配置下拉
const users = ref([]); // [{name,userId}]
const projects = ref([]); // [{name,projectId}]

// 新页面：只展示执行者下拉；userId/projectId 走默认值
const operatorUserId = ref("");
const projectId = ref("");
const executorId = ref("");

// 新页面：调休天数（用于从“有效工作日天数”扣减）
const restDays = ref(0);

// 统计结果/输出
const analysisLoading = ref(false);
const analysisOut = ref("");

// 更新数据 loading（给“更新数据”按钮用）
const updateLoading = ref(false);

// 工时折算系数：从数据库 config 表读取（兜底 0.7）
const workhourCoefficient = ref(WORKHOUR_COEFFICIENT);
const executorCharacter = ref(null);

function buildTbTaskUrl(taskId) {
  const tid = String(taskId || "").trim();
  if (!tid) return "";
  return `https://www.teambition.com/task/${encodeURIComponent(tid)}`;
}

function splitBreakdownRows(d) {
  const rows = Array.isArray(d?.breakdown) ? d.breakdown : [];
  const normalRows = [];
  const overdueRows = [];
  for (const row of rows) {
    const taskId = String(row?.taskId ?? "").trim();
    const content = String(row?.content ?? "").trim();
    const name = content || taskId || "—";
    const h = row?.work_hour;
    const workHour =
      h != null && typeof h === "number" && Number.isFinite(h) ? h : null;
    const item = { taskId, name, workHour };
    if (row?.is_overdue) overdueRows.push(item);
    else normalRows.push(item);
  }
  return { normalRows, overdueRows };
}

function computeInclusiveDays(ds, de) {
  const t0 = new Date(`${ds.slice(0, 10)}T12:00:00`).getTime();
  const t1 = new Date(`${de.slice(0, 10)}T12:00:00`).getTime();
  if (Number.isNaN(t0) || Number.isNaN(t1)) return null;
  if (t1 < t0) return null;
  return Math.round((t1 - t0) / 86400000) + 1;
}

/**
 * 顶部信息：
 * - “法定节假日天数”：按区间总天数 - countWorkdays 得到（countWorkdays 包含调休补班）
 * - “调休天数”：用户输入的附加扣减天数
 */
const holidaySummary = computed(() => {
  const s = (dueDateStart.value || "").trim();
  const e = (dueDateEnd.value || "").trim();
  if (!s || !e) {
    return { state: "pending", text: "未设置日期区间", holidayDays: null, workdays: null };
  }
  const ds = s.slice(0, 10);
  const de = e.slice(0, 10);
  const totalDays = computeInclusiveDays(ds, de);
  if (totalDays == null) return { state: "error", text: "日期无效", holidayDays: null, workdays: null };

  try {
    const workdays = countWorkdays(ds, de);
    const holidayDays = Math.max(0, totalDays - workdays);
    return {
      state: "ok",
      text: `${ds} 至 ${de}，法定节假日天数（按国务院放假）为 ${holidayDays} 天`,
      holidayDays,
      workdays,
      totalDays,
    };
  } catch {
    return {
      state: "error",
      text: "无法计算（日期可能超出节假日数据范围，约 2011–2026 年）",
      holidayDays: null,
      workdays: null,
    };
  }
});

const effectiveWorkdays = computed(() => {
  if (holidaySummary.value.state !== "ok" || typeof holidaySummary.value.workdays !== "number") return null;
  return Math.max(0, holidaySummary.value.workdays - restDaysEffective.value);
});

const restDaysEffective = computed(() => {
  const r = Number(restDays.value);
  return Number.isFinite(r) && r > 0 ? r : 0;
});

const expectedWorkhours = computed(() => {
  if (effectiveWorkdays.value == null) return null;
  const c = Number(workhourCoefficient.value);
  const v = effectiveWorkdays.value * (Number.isFinite(c) ? c : WORKHOUR_COEFFICIENT);
  return Math.round(v * 100) / 100;
});

const executorActualTotalWorkhours = ref(null);
const executorOverdueTotalWorkhours = ref(null);
const quarterBreakdownRows = ref([]);
const overdueBreakdownRows = ref([]);
const quarterBreakdownSum = computed(() => {
  let s = 0;
  for (const r of quarterBreakdownRows.value) {
    if (typeof r.workHour === "number" && Number.isFinite(r.workHour)) s += r.workHour;
  }
  return Math.round(s * 100) / 100;
});
const overdueBreakdownSum = computed(() => {
  let s = 0;
  for (const r of overdueBreakdownRows.value) {
    if (typeof r.workHour === "number" && Number.isFinite(r.workHour)) s += r.workHour;
  }
  return Math.round(s * 100) / 100;
});
const executorCompletedTotalWorkhours = computed(() => {
  const a = executorActualTotalWorkhours.value;
  const o = executorOverdueTotalWorkhours.value;
  if (
    typeof a !== "number" || !Number.isFinite(a) ||
    typeof o !== "number" || !Number.isFinite(o)
  ) return null;
  return Math.round((a + o) * 100) / 100;
});
const completionRatioPercent = computed(() => {
  const expected = expectedWorkhours.value;
  const done = executorCompletedTotalWorkhours.value;
  if (
    typeof expected !== "number" || !Number.isFinite(expected) || expected <= 0 ||
    typeof done !== "number" || !Number.isFinite(done)
  ) return null;
  return Math.round((done / expected) * 10000) / 100;
});
const completionRatioColor = computed(() => {
  const p = completionRatioPercent.value;
  if (typeof p !== "number" || !Number.isFinite(p)) return "#909399";
  if (p >= 100) return "#67c23a";
  if (p >= 71.5) return "#e6a23c";
  return "#f56c6c";
});
const analysisDiff = computed(() => {
  const expected = expectedWorkhours.value;
  const done = executorCompletedTotalWorkhours.value;
  if (
    typeof expected !== "number" || !Number.isFinite(expected) ||
    typeof done !== "number" || !Number.isFinite(done)
  ) return null;
  // 差额 = 工时合计 - 所需工时
  return Math.round((done - expected) * 100) / 100;
});
const analysisDiffColor = computed(() => {
  const d = analysisDiff.value;
  if (typeof d !== "number" || !Number.isFinite(d)) return "#909399";
  // 负数红，正数绿
  if (d >= 0) return "#67c23a";
  return "#f56c6c";
});
const hasAnalysisResult = ref(false);

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

  if (!operatorUserId.value) operatorUserId.value = firstUserId;
  if (!executorId.value) executorId.value = firstUserId;
  if (!projectId.value) projectId.value = projects.value?.[0]?.projectId || "";
}

async function reloadTimeRange() {
  const resp = await apiFetch("/api/bt/config/time_range");
  const d = (resp && resp.data) || {};
  const st = d.start_time || "";
  const et = d.end_time || "";
  lastUpdateTime.value = d.last_update_time || "";

  if (st) dueDateStart.value = isoToDatetimeLocal(st) || dueDateStart.value;
  if (et) dueDateEnd.value = isoToDatetimeLocal(et) || dueDateEnd.value;
}

async function reloadWorkhourAutoCalc() {
  const resp = await apiFetch("/api/bt/config/workhour_auto_calc");
  const d = (resp && resp.data) || {};
  autoCalcEnabled.value = !!d.auto_calc_enabled;
  autoCalcTime.value = d.auto_calc_time || "09:00";
}

async function reloadExecutorCharacterAndCoefficient(userId) {
  const uid = String(userId || "").trim();
  if (!uid) {
    executorCharacter.value = null;
    workhourCoefficient.value = WORKHOUR_COEFFICIENT;
    return;
  }

  const resp = await apiFetch(
    `/api/bt/config/user_character?userId=${encodeURIComponent(uid)}`,
  );
  const d = (resp && resp.data) || {};
  executorCharacter.value =
    typeof d.character === "number" ? d.character : Number(d.character) || 0;
  const coef = Number(d.workhour_coefficient);
  workhourCoefficient.value =
    Number.isFinite(coef) && coef >= 0 ? coef : WORKHOUR_COEFFICIENT;
}

watch(
  executorId,
  async (v) => {
    try {
      await reloadExecutorCharacterAndCoefficient(v);
    } catch (e) {
      // 兜底：计算仍可用默认 0.7，不阻断页面
      executorCharacter.value = null;
      workhourCoefficient.value = WORKHOUR_COEFFICIENT;
    }
  },
  { immediate: true },
);

async function doWorkhourAnalysis(opts = {}) {
  if (updateLoading.value) {
    ElMessage.warning("正在更新数据，请稍候。");
    return;
  }
  const _forceRefreshList = !!opts.forceRefreshList;
  analysisLoading.value = true;
  try {
    hasAnalysisResult.value = false;
    executorActualTotalWorkhours.value = null;
    executorOverdueTotalWorkhours.value = null;
    quarterBreakdownRows.value = [];
    overdueBreakdownRows.value = [];
    analysisOut.value = "工时分析中...";

    const pid = (projectId.value || "").trim();
    const ex = (executorId.value || "").trim();
    if (!pid) {
      ElMessage.warning("请选择项目。");
      return;
    }
    if (!ex) {
      ElMessage.warning("请选择执行者。");
      return;
    }

    const startTime = toIsoForQueryStart(dueDateStart.value || "");
    const endTime = toIsoForQueryEnd(dueDateEnd.value || "");
    if (!startTime || !endTime) {
      ElMessage.warning("开始时间/结束时间无效，请先在设置中检查时间区间。");
      return;
    }

    const res = await apiFetch("/api/bt/stats/executor_quarter_workhours", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        projectId: pid,
        executorId: ex,
        start_time: startTime,
        end_time: endTime,
      }),
    });

    const d = (res && res.data) || {};
    const { normalRows, overdueRows } = splitBreakdownRows(d);
    quarterBreakdownRows.value = normalRows;
    overdueBreakdownRows.value = overdueRows;
    const quarter = d.quarter_work_hour;
    const overdue = d.quarter_overdue_work_hour;
    executorActualTotalWorkhours.value =
      typeof quarter === "number" && Number.isFinite(quarter) ? quarter : null;
    executorOverdueTotalWorkhours.value =
      typeof overdue === "number" && Number.isFinite(overdue) ? overdue : null;

    hasAnalysisResult.value = true;
    analysisOut.value = "";

    const hasBreakdown = Array.isArray(d?.breakdown) && d.breakdown.length > 0;
    const qv = typeof quarter === "number" && Number.isFinite(quarter) ? quarter : 0;
    const ov =
      typeof overdue === "number" && Number.isFinite(overdue) ? overdue : 0;

    if (!hasBreakdown && qv === 0 && ov === 0) {
      ElMessage.warning("本时间窗内未查询到工时数据，请先点击“更新数据”。");
      analysisOut.value = "（提示：无匹配任务明细，可能需要更新数据库后再分析。）";
      return;
    }

    ElMessage.success(`工时分析完成：季度工时 ${executorActualTotalWorkhours.value ?? "—"}`);
  } catch (e) {
    showErr((t) => (analysisOut.value = t), e);
    hasAnalysisResult.value = false;
    executorActualTotalWorkhours.value = null;
    executorOverdueTotalWorkhours.value = null;
    quarterBreakdownRows.value = [];
    overdueBreakdownRows.value = [];
  } finally {
    analysisLoading.value = false;
  }
}

async function doUpdateData() {
  if (updateLoading.value) return;
  if (!operatorUserId.value || !projectId.value) {
    ElMessage.warning("缺少操作者/项目配置，请先确保页面加载正常。");
    return;
  }

  updateLoading.value = true;
  try {
    // 1) 按 config.start_time/end_time 拉列表并同步 A+B（软件开发场景）
    await apiFetch("/api/bt/query_project_tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: String(operatorUserId.value).trim(),
        projectId: String(projectId.value).trim(),
        // 后端会读取 config.start_time/end_time 生成 query，并同步 A+B
        sync_ab_by_config_time_range: true,
      }),
    });

    // 2) 同步完成后更新 last_update_time（供 UI 展示）
    const resp = await apiFetch("/api/bt/config/touch_last_update_time", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = (resp && resp.data) || {};
    lastUpdateTime.value = d.last_update_time || lastUpdateTime.value;

    // 3) 立即刷新 config.start_time/end_time（避免“法定工作日”滞后）
    await reloadTimeRange();

    ElMessage.success("更新数据完成。");
  } catch (e) {
    showErr((t) => (analysisOut.value = t), e);
    ElMessage.error(e && e.message ? e.message : "更新数据失败");
  } finally {
    updateLoading.value = false;
  }
}

async function doFullUpdateData() {
  if (updateLoading.value) return;
  if (!operatorUserId.value || !projectId.value) {
    ElMessage.warning("缺少操作者/项目配置，请先确保页面加载正常。");
    return;
  }

  updateLoading.value = true;
  try {
    // 全量更新：按 end_time 往前一年窗口，同步 A+B+C(overdue)
    await apiFetch("/api/bt/full_update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: String(operatorUserId.value).trim(),
        projectId: String(projectId.value).trim(),
        // 这里跟后端默认值一致；你需要更大数据量再改
        maxResults: 500,
        maxPages: 200,
      }),
    });

    const resp = await apiFetch("/api/bt/config/touch_last_update_time", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = (resp && resp.data) || {};
    lastUpdateTime.value = d.last_update_time || lastUpdateTime.value;
    await reloadTimeRange();

    ElMessage.success("全量更新完成。");
  } catch (e) {
    showErr((t) => (analysisOut.value = t), e);
    ElMessage.error(e && e.message ? e.message : "全量更新失败");
  } finally {
    updateLoading.value = false;
  }
}

function openSettings() {
  if (updateLoading.value) {
    ElMessage.warning("正在更新数据，请稍候。");
    return;
  }
  settingsDueDateStart.value = dueDateStart.value;
  settingsDueDateEnd.value = dueDateEnd.value;
  settingsAutoCalcEnabled.value = autoCalcEnabled.value;
  settingsAutoCalcTime.value = autoCalcTime.value;
  showSettings.value = true;
}

async function doSaveSettings() {
  if (updateLoading.value) {
    ElMessage.warning("正在更新数据，请稍候。");
    return;
  }
  if (!settingsDueDateStart.value || !settingsDueDateEnd.value) {
    ElMessage.warning("请先填写开始时间和结束时间。");
    return;
  }

  const stIso = toIsoFromDatetimeLocal(settingsDueDateStart.value);
  const etIso = toIsoFromDatetimeLocal(settingsDueDateEnd.value);
  await apiFetch("/api/bt/config/time_range", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_time: stIso, end_time: etIso }),
  });

  await apiFetch("/api/bt/config/workhour_auto_calc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enabled: settingsAutoCalcEnabled.value,
      auto_time: settingsAutoCalcTime.value,
    }),
  });

  // 更新主界面展示用的时间范围/开关
  dueDateStart.value = settingsDueDateStart.value;
  dueDateEnd.value = settingsDueDateEnd.value;
  autoCalcEnabled.value = settingsAutoCalcEnabled.value;
  autoCalcTime.value = settingsAutoCalcTime.value;

  showSettings.value = false;
  ElMessage.success("设置已保存。");
}

let _lastRefreshTimer = null;
onMounted(async () => {
  try {
    // 进入页面先读 config 的时间区间，确保“法定工作日”按配置计算并立即展示
    await reloadTimeRange();
    await reloadConfigOptions();
    await reloadWorkhourAutoCalc();
    analysisOut.value = "就绪（选择执行者后点击“工时分析”）。";

    // 轮询 last_update_time，让“自动计算/更新数据”可在页面上感知到
    _lastRefreshTimer = setInterval(() => {
      reloadTimeRange().catch(() => {});
    }, 60000);
  } catch (e) {
    showErr((t) => (analysisOut.value = t), e);
  }
});

onBeforeUnmount(() => {
  if (_lastRefreshTimer) clearInterval(_lastRefreshTimer);
});
</script>

<template>
  <div class="page">
    <div class="header">
      <h1>本体开发部</h1>
    </div>

    <div class="main">
      <el-card shadow="never">
        <template #header>
          <div
            style="
              display: flex;
              justify-content: space-between;
              align-items: center;
              gap: 12px;
              flex-wrap: wrap;
              width: 100%;
            "
          >
            <div style="font-weight: 700">工时分析</div>
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap">
              <el-button
                type="warning"
                :loading="updateLoading"
                :disabled="updateLoading || analysisLoading"
                @click="doFullUpdateData"
              >
                全量更新
              </el-button>
              <el-button
                type="warning"
                :loading="updateLoading"
                :disabled="updateLoading || analysisLoading"
                @click="doUpdateData"
              >
                更新数据
              </el-button>
              <el-button
                circle
                type="warning"
                :icon="Setting"
                @click="openSettings"
                aria-label="设置"
                :disabled="updateLoading || analysisLoading"
              />
              <div style="font-size: 12px; color: #606266">
                上次更新时间：{{ lastUpdateTimeDisplay }}
              </div>
            </div>
          </div>
        </template>
        <el-dialog
          v-model="showSettings"
          title="设置"
          width="720px"
          destroy-on-close
        >
          <el-form label-position="top">
            <el-row :gutter="12">
              <el-col :xs="24" :md="12">
                <el-form-item label="开始时间">
                  <el-input v-model="settingsDueDateStart" type="datetime-local" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="12">
                <el-form-item label="结束时间">
                  <el-input v-model="settingsDueDateEnd" type="datetime-local" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="自动计算开关">
              <el-switch v-model="settingsAutoCalcEnabled" />
            </el-form-item>

            <el-form-item label="自动计算时间">
              <el-time-picker
                v-model="settingsAutoCalcTime"
                type="time"
                format="HH:mm"
                value-format="HH:mm"
                :disabled="!settingsAutoCalcEnabled"
                placeholder="选择时间"
              />
            </el-form-item>

            <div style="text-align: right; margin-top: 12px">
              <el-button
                :disabled="updateLoading"
                @click="showSettings = false"
              >
                取消
              </el-button>
              <el-button
                type="primary"
                :disabled="updateLoading"
                @click="doSaveSettings"
              >
                保存
              </el-button>
            </div>
          </el-form>
        </el-dialog>

        <div
          style="
            display: flex;
            flex-wrap: wrap;
            gap: 10px 14px;
            align-items: center;
            justify-content: flex-start;
            margin-bottom: 10px;
          "
        >
          <div style="display: flex; align-items: center; gap: 8px">
            <span style="font-size: 14px; color: #606266">开始时间</span>
            <el-input
              :model-value="dueDateStart ? dueDateStart.replace('T', ' ') : ''"
              disabled
              size="small"
              placeholder="—"
              style="width: 220px"
            />
          </div>
          <div style="display: flex; align-items: center; gap: 8px">
            <span style="font-size: 14px; color: #606266">结束时间</span>
            <el-input
              :model-value="dueDateEnd ? dueDateEnd.replace('T', ' ') : ''"
              disabled
              size="small"
              placeholder="—"
              style="width: 220px"
            />
          </div>
        </div>

        <div
          class="statutory-workday-bar"
          :data-state="holidaySummary.state"
        >
          <div class="statutory-workday-bar__main">
            <span class="statutory-workday-bar__text">
              法定工作日天数（含调休）：
              <strong>{{ holidaySummary.workdays ?? "—" }}</strong> 天
            </span>
            <span class="statutory-workday-bar__leave-wrap">
              <span class="statutory-workday-bar__leave-label">调休天数（天）</span>
              <el-input-number
                v-model="restDays"
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
            v-if="holidaySummary.state === 'ok' && expectedWorkhours !== null"
            class="statutory-workday-bar__result"
          >
            <div class="statutory-workday-bar__result-row">
              <span class="statutory-workday-bar__result-days">
                工时系数：
                <strong>{{ workhourCoefficient }}</strong>
                <span class="statutory-workday-bar__formula">
                  （所需工时 = （法定工作日天数 {{ holidaySummary.workdays }} - 调休天数 {{ restDaysEffective }}）× 工时系数
                  {{ workhourCoefficient }}）
                </span>
              </span>
              <span class="statutory-workday-bar__result-hours">
                所需工时：
                <strong>{{ expectedWorkhours }}</strong>
              </span>
            </div>
          </div>
        </div>

        <el-form label-position="top" style="margin-top: 12px">
          <el-form-item label="执行者（必填）">
            <el-select
              v-model="executorId"
              filterable
              placeholder="请选择执行者"
              style="width: 100%"
            >
              <el-option
                v-for="u in users"
                :key="u.userId"
                :label="u.name"
                :value="u.userId"
              />
            </el-select>
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              :loading="analysisLoading"
              :disabled="updateLoading"
              @click="doWorkhourAnalysis"
            >
              工时分析
            </el-button>
          </el-form-item>
        </el-form>

        <div v-if="hasAnalysisResult" style="margin-top: 12px">
          <el-row :gutter="12">
            <el-col :xs="24" :md="12">
              <el-card shadow="never">
                <template #header>
                  <div style="font-weight: 700">工时概览</div>
                </template>
                <div style="display: grid; grid-template-columns: 120px 1fr; row-gap: 8px; column-gap: 8px; font-size: 14px">
                  <div style="color: #909399">区间</div>
                  <div>{{ dueDateStart.slice(0, 10) }} 至 {{ dueDateEnd.slice(0, 10) }}</div>
                  <div style="color: #909399">法定工作日</div>
                  <div>{{ holidaySummary.workdays ?? "—" }} 天</div>
                  <div style="color: #909399">调休天数</div>
                  <div>{{ restDaysEffective ?? "—" }} 天</div>
                  <div style="color: #909399">工时系数</div>
                  <div>{{ workhourCoefficient }}</div>
                </div>
              </el-card>
            </el-col>

            <el-col :xs="24" :md="12">
              <el-card shadow="never">
                <template #header>
                  <div style="font-weight: 700">计算结果</div>
                </template>
                <div style="display: grid; grid-template-columns: 150px 1fr; row-gap: 8px; column-gap: 8px; font-size: 14px">
                  <div style="color: #909399">所需工时</div>
                  <div><strong>{{ expectedWorkhours ?? "—" }}</strong></div>
                  <div style="color: #909399">季度工时</div>
                  <div>{{ executorActualTotalWorkhours ?? "—" }}</div>
                  <div style="color: #909399">季度逾期</div>
                  <div>{{ executorOverdueTotalWorkhours ?? "—" }}</div>
                  <div style="color: #909399">工时合计</div>
                  <div>{{ executorCompletedTotalWorkhours ?? "—" }}</div>
                  <div style="color: #909399">差额</div>
                  <div><strong :style="{ color: analysisDiffColor }">{{ analysisDiff ?? "—" }}</strong></div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <div v-if="quarterBreakdownRows.length || overdueBreakdownRows.length" style="margin-top: 12px">
          <el-row :gutter="12">
            <el-col :xs="24" :md="12">
              <el-card shadow="never">
                <template #header>
                  <div style="font-weight: 700">季度工时明细</div>
                </template>
                <el-table :data="quarterBreakdownRows" size="small" border>
                  <el-table-column prop="name" label="任务" min-width="220">
                    <template #default="{ row }">
                      <a
                        v-if="row?.taskId"
                        :href="buildTbTaskUrl(row.taskId)"
                        target="_blank"
                        rel="noopener noreferrer"
                        style="color: inherit; text-decoration: underline"
                      >
                        {{ row.name }}
                      </a>
                      <span v-else>{{ row?.name ?? "—" }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="工时" width="110" align="right">
                    <template #default="{ row }">
                      {{ row.workHour ?? "—" }}
                    </template>
                  </el-table-column>
                </el-table>
                <div style="margin-top: 8px; text-align: right; font-size: 13px">
                  合计：<strong>{{ quarterBreakdownSum }}</strong>
                </div>
              </el-card>
            </el-col>

            <el-col :xs="24" :md="12">
              <el-card shadow="never">
                <template #header>
                  <div style="font-weight: 700">季度逾期明细</div>
                </template>
                <el-table :data="overdueBreakdownRows" size="small" border>
                  <el-table-column prop="name" label="任务" min-width="220">
                    <template #default="{ row }">
                      <a
                        v-if="row?.taskId"
                        :href="buildTbTaskUrl(row.taskId)"
                        target="_blank"
                        rel="noopener noreferrer"
                        style="color: inherit; text-decoration: underline"
                      >
                        {{ row.name }}
                      </a>
                      <span v-else>{{ row?.name ?? "—" }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="工时" width="110" align="right">
                    <template #default="{ row }">
                      {{ row.workHour ?? "—" }}
                    </template>
                  </el-table-column>
                </el-table>
                <div style="margin-top: 8px; text-align: right; font-size: 13px">
                  合计：<strong>{{ overdueBreakdownSum }}</strong>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <div class="out" v-if="analysisOut">{{ analysisOut }}</div>
      </el-card>
    </div>
  </div>
</template>

