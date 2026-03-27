const DEFAULT_API_BASE = "http://127.0.0.1:5001";
const API_BASE_KEY = "tb_tool_b1_api_base";

const DEV_SCENARIO_ID = "647854bcd999c893061ef8b5"; // 软件开发
const TARGET_WORKHOUR_FIELD_ID = "64c8cad8485fb3987a5521b8";

const el = (id) => document.getElementById(id);

const apiBaseInput = el("apiBaseInput");
const btnSaveApiBase = el("btnSaveApiBase");
const btnHealth = el("btnHealth");
const btnGetToken = el("btnGetToken");

const projectUserSelect = el("projectUserSelect");
const projectIdSelect = el("projectIdSelect");
const dueDateStartInput = el("dueDateStartInput");
const dueDateEndInput = el("dueDateEndInput");
const btnProjectTaskQuery = el("btnProjectTaskQuery");
const projectOutEl = el("projectOut");
const projectMetaHint = el("projectMetaHint");

const taskUserSelect = el("taskUserSelect");
const taskExecutorSelect = el("taskExecutorSelect");
const taskFilterInput = el("taskFilterInput");
const taskIdSelect = el("taskIdSelect");
const parentTaskIdInput = el("parentTaskIdInput");
const btnUserTaskQuery = el("btnUserTaskQuery");
const btnAccurateWorkhour = el("btnAccurateWorkhour");
const taskOutEl = el("taskOut");

const taskOptionHint = el("taskOptionHint");
const workhourHint = el("workhourHint");
const accurateWorkhourProgress = el("accurateWorkhourProgress");
const workhourDetailOut = el("workhourDetailOut");
const workhourDebugToggle = el("workhourDebugToggle");
const workhourDebugOut = el("workhourDebugOut");

let allTaskOptions = [];
let allTaskRawRows = [];
let currentFilteredTaskIds = [];

function getApiBase() {
  const v = (localStorage.getItem(API_BASE_KEY) || "").trim();
  return v || DEFAULT_API_BASE;
}

function setApiBase(v) {
  localStorage.setItem(API_BASE_KEY, String(v || "").trim());
}

function joinUrl(base, path) {
  const b = (base || "").replace(/\/+$/, "");
  const p = String(path || "").startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

async function apiFetch(path, init) {
  const url = joinUrl(getApiBase(), path);
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (data && data.error) ? data.error : `HTTP ${res.status}`;
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
  const v = (dueDateStartInput.value || "").trim();
  if (!v) return;
  const d = v.slice(0, 10);
  if (!d) return;
  dueDateStartInput.value = `${d}T00:00:00`;
}

function forceEndDayTime() {
  const v = (dueDateEndInput.value || "").trim();
  if (!v) return;
  const d = v.slice(0, 10);
  if (!d) return;
  dueDateEndInput.value = `${d}T23:59:59`;
}

function buildProjectQuery() {
  const start = (dueDateStartInput.value || "").trim();
  const end = (dueDateEndInput.value || "").trim();
  const clauses = [];
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

function fillTaskIdOptionsFromProjectResult(resp) {
  const dingtalk = ((((resp || {}).data || {}).data || {}).dingtalk) || {};
  let out = [];
  if (Array.isArray(dingtalk.result)) {
    allTaskRawRows = dingtalk.result;
    out = dingtalk.result
      .map((x) => ({
        id: x && x.taskId ? String(x.taskId) : "",
        name: x && x.content ? String(x.content) : "",
        executorId: x && x.executorId ? String(x.executorId) : "",
      }))
      .filter((x) => x.id);
  } else {
    allTaskRawRows = [];
    out = [];
  }

  const dedup = {};
  out.forEach((x) => {
    if (!dedup[x.id]) dedup[x.id] = x;
  });
  const items = Object.keys(dedup).map((k) => dedup[k]);
  allTaskOptions = items;

  renderTaskSelectOptions(taskFilterInput.value);
  updateWorkhourSummary();
}

function getTargetWorkhourField(row) {
  const fields = row.customFields || row.customfields || [];
  if (!Array.isArray(fields)) return null;
  for (let i = 0; i < fields.length; i += 1) {
    const f = fields[i] || {};
    const fid = f.customFieldId || f.customfieldId;
    if (String(fid || "") === TARGET_WORKHOUR_FIELD_ID) return f;
  }
  return null;
}

function parseWorkhourFromTaskRow(row) {
  const f = getTargetWorkhourField(row || {});
  if (!f) return 0;

  let vals = f.value;
  if (vals === undefined || vals === null) return 0;

  if (typeof vals === "string") {
    try {
      vals = JSON.parse(vals);
    } catch (e) {
      vals = [];
    }
  }

  const parseFrom = (x) => {
    if (x === undefined || x === null) return 0;
    if (typeof x === "number") return Number.isFinite(x) ? x : 0;
    if (typeof x === "string") {
      const m = x.match(/-?\d+(\.\d+)?/);
      if (m) {
        const n = Number(m[0]);
        return Number.isFinite(n) ? n : 0;
      }
      const n = Number(x);
      return Number.isFinite(n) ? n : 0;
    }
    const n2 = Number(x);
    return Number.isFinite(n2) ? n2 : 0;
  };

  if (Array.isArray(vals)) {
    if (vals.length === 0) return 0;
    const v0 = vals[0] || {};
    return parseFrom(
      v0.title !== undefined
        ? v0.title
        : v0.value !== undefined
          ? v0.value
          : v0.numberValue
    );
  }

  if (typeof vals === "object") {
    const maybeTitle = vals.title !== undefined ? vals.title : vals.value;
    return parseFrom(maybeTitle);
  }

  return 0;
}

function updateWorkhourSummary() {
  const executorId = (taskExecutorSelect.value || "").trim();
  const rows = executorId
    ? allTaskRawRows.filter((r) => String((r && r.executorId) || "") === executorId)
    : allTaskRawRows;

  let total = 0;
  let hit = 0;
  let hasFieldCount = 0;
  let valuePresentCount = 0;

  const debugRows = [];
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i] || {};
    const v = parseWorkhourFromTaskRow(row);
    if (v > 0) hit += 1;
    total += v;

    const targetField = getTargetWorkhourField(row);
    const hasTarget = !!targetField;
    if (hasTarget) hasFieldCount += 1;
    const targetVal = targetField ? targetField.value : undefined;
    const valuePresent = !(targetVal === undefined || targetVal === null);
    if (hasTarget && valuePresent) valuePresentCount += 1;

    if (i < 20) {
      debugRows.push({
        taskId: row.taskId || "",
        content: row.content || "",
        executorId: row.executorId || "",
        hasTargetField: hasTarget,
        parsedWorkhour: v,
        hasValue: valuePresent,
        targetValue: targetVal,
      });
    }
  }

  workhourHint.textContent = `有效工时合计：${total}（筛选任务：${rows.length}，含字段任务：${hasFieldCount}，含值任务：${valuePresentCount}，非零命中：${hit}）`;

  if (workhourDebugToggle.checked) {
    workhourDebugOut.style.display = "block";
    workhourDebugOut.textContent = JSON.stringify(
      {
        targetFieldId: TARGET_WORKHOUR_FIELD_ID,
        filteredCount: rows.length,
        hitCount: hit,
        totalWorkhour: total,
        valuePresentCount,
        sample: debugRows,
      },
      null,
      2
    );
  } else {
    workhourDebugOut.style.display = "none";
  }
}

function renderTaskSelectOptions(keyword) {
  const kw = (keyword || "").trim();
  const executorId = (taskExecutorSelect.value || "").trim();
  let items = allTaskOptions;
  if (executorId) items = items.filter((x) => (x.executorId || "") === executorId);
  if (kw) items = items.filter((x) => x.name.includes(kw) || x.id.includes(kw));

  currentFilteredTaskIds = items.map((x) => x.id);

  taskIdSelect.innerHTML = "";
  if (items.length === 0) {
    const op = document.createElement("option");
    op.value = "";
    op.textContent = kw ? "无匹配项" : "请先在左侧查询项目任务";
    taskIdSelect.appendChild(op);
    taskOptionHint.textContent = "任务候选：0";
    return;
  }

  items.forEach((item) => {
    const op = document.createElement("option");
    op.value = item.id;
    op.textContent = `${item.name}（${item.id}）`;
    taskIdSelect.appendChild(op);
  });
  taskIdSelect.value = items[0].id;
  taskOptionHint.textContent = `任务候选：${items.length}`;
}

function resolveTaskIdFromInput() {
  return (taskIdSelect.value || "").trim();
}

async function loadUserOptions() {
  const data = await apiFetch("/api/b1/config/userids");
  const users = (((data || {}).data || {}).users) || [];
  const DEFAULT_USER_NAME = "邹宏睿";

  // 清空旧的（避免重复）
  projectUserSelect.innerHTML = '<option value="">请选择人员</option>';
  taskUserSelect.innerHTML = '<option value="">请选择人员</option>';
  taskExecutorSelect.innerHTML = '<option value="">执行者：全部</option>';

  users.forEach((u) => {
    const op1 = document.createElement("option");
    op1.value = u.userId;
    op1.textContent = `${u.name} (${u.userId})`;
    projectUserSelect.appendChild(op1);

    const op2 = document.createElement("option");
    op2.value = u.userId;
    op2.textContent = `${u.name} (${u.userId})`;
    taskUserSelect.appendChild(op2);

    const op3 = document.createElement("option");
    op3.value = u.userId;
    op3.textContent = `${u.name} (${u.userId})`;
    taskExecutorSelect.appendChild(op3);
  });

  const zhr = users.find((x) => String(x && x.name) === DEFAULT_USER_NAME);
  if (zhr && zhr.userId) {
    projectUserSelect.value = zhr.userId;
    taskUserSelect.value = zhr.userId;
    taskExecutorSelect.value = zhr.userId;
    return;
  }
  if (users.length > 0) {
    projectUserSelect.value = users[0].userId;
    taskUserSelect.value = users[0].userId;
    taskExecutorSelect.value = users[0].userId;
  }
}

async function loadProjectOptions() {
  const data = await apiFetch("/api/b1/config/projectids");
  const projects = (((data || {}).data || {}).projects) || [];

  projectIdSelect.innerHTML = '<option value="">请选择项目</option>';
  projects.forEach((p) => {
    const op = document.createElement("option");
    op.value = p.projectId;
    op.textContent = `${p.name}（${p.projectId}）`;
    projectIdSelect.appendChild(op);
  });
  if (projects.length > 0) projectIdSelect.value = projects[0].projectId;
}

async function postTaskQuery(payload) {
  return apiFetch("/api/b1/project/tasks/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

async function postUserTaskQuery(payload) {
  return apiFetch("/api/b1/tasks/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

async function accurateWorkhourByTaskIdsSequential(taskIds, userId) {
  let total = 0;
  let hit = 0;

  const nameMap = {};
  for (let i = 0; i < allTaskOptions.length; i += 1) {
    const it = allTaskOptions[i];
    if (it && it.id) nameMap[it.id] = it.name || "";
  }

  const DETAIL_LIMIT = 200;
  const detailRows = [];
  for (let i = 0; i < taskIds.length; i += 1) {
    const taskId = taskIds[i];
    accurateWorkhourProgress.textContent = `精确统计：${i + 1}/${taskIds.length}（taskId=${taskId}）`;

    const payload = {
      userId,
      taskId,
      parentTaskId: (parentTaskIdInput.value || "").trim(),
    };
    const resp = await postUserTaskQuery(payload);
    const dingtalk = ((((resp || {}).data || {}).data || {}).dingtalk) || {};

    let row = null;
    if (Array.isArray(dingtalk.result)) row = dingtalk.result[0] || null;
    else if (dingtalk.result) row = dingtalk.result;

    const v = parseWorkhourFromTaskRow(row || {});
    if (v > 0) hit += 1;
    total += v;

    if (detailRows.length < DETAIL_LIMIT) {
      detailRows.push({
        taskId: String(taskId),
        taskName: nameMap[String(taskId)] || "",
        workhour: v,
      });
    }

    await new Promise((r) => setTimeout(r, 0));
  }

  return { total, hit, count: taskIds.length, detailRows, detailLimit: DETAIL_LIMIT };
}

function showErr(whereEl, err) {
  const msg = (err && err.message) ? err.message : String(err);
  whereEl.textContent = `错误：${msg}\n（后端地址：${getApiBase()}）`;
}

// -------- events --------
btnSaveApiBase.addEventListener("click", async () => {
  try {
    setApiBase(apiBaseInput.value);
    projectOutEl.textContent = "已保存后端地址，重新加载下拉…";
    taskOutEl.textContent = "已保存后端地址，重新加载下拉…";
    await Promise.all([loadUserOptions(), loadProjectOptions()]);
    projectOutEl.textContent = "就绪。";
    taskOutEl.textContent = "就绪。";
  } catch (e) {
    showErr(projectOutEl, e);
    showErr(taskOutEl, e);
  }
});

btnHealth.addEventListener("click", async () => {
  try {
    projectOutEl.textContent = "健康检查中...";
    taskOutEl.textContent = "健康检查中...";
    const data = await apiFetch("/api/b1/health");
    projectOutEl.textContent = prettyJsonWithLimit(data);
    taskOutEl.textContent = prettyJsonWithLimit(data);
  } catch (e) {
    showErr(projectOutEl, e);
    showErr(taskOutEl, e);
  }
});

btnGetToken.addEventListener("click", async () => {
  try {
    projectOutEl.textContent = "获取 token 中...";
    taskOutEl.textContent = "获取 token 中...";
    const data = await apiFetch("/api/b1/gettoken", { method: "POST" });
    projectOutEl.textContent = prettyJsonWithLimit(data);
    taskOutEl.textContent = prettyJsonWithLimit(data);
  } catch (e) {
    showErr(projectOutEl, e);
    showErr(taskOutEl, e);
  }
});

btnProjectTaskQuery.addEventListener("click", async () => {
  try {
    projectOutEl.textContent = "查询项目任务中...";
    projectMetaHint.textContent = "请求中…";

    const payload = {
      userId: (projectUserSelect.value || "").trim(),
      projectId: (projectIdSelect.value || "").trim(),
      query: buildProjectQuery(),
      maxResults: 500,
    };
    if (!payload.userId || !payload.projectId) {
      projectOutEl.textContent = "请先选择人员和项目。";
      projectMetaHint.textContent = "缺少必填字段";
      return;
    }

    const data = await postTaskQuery(payload);
    const softwareOnlyData = filterSoftwareOnly(data);
    projectOutEl.textContent = prettyJsonWithLimit(softwareOnlyData);

    // 元信息小提示
    const dingtalk = ((((softwareOnlyData || {}).data || {}).data || {}).dingtalk) || {};
    const total = Array.isArray(dingtalk.result) ? dingtalk.result.length : 0;
    projectMetaHint.textContent = `已加载（软件开发过滤后）：${total} 条`;

    setTimeout(() => fillTaskIdOptionsFromProjectResult(softwareOnlyData), 0);
  } catch (e) {
    showErr(projectOutEl, e);
    projectMetaHint.textContent = "失败";
  }
});

btnUserTaskQuery.addEventListener("click", async () => {
  try {
    taskOutEl.textContent = "查询任务中...";
    const payload = {
      userId: (taskUserSelect.value || "").trim(),
      taskId: resolveTaskIdFromInput(),
      parentTaskId: (parentTaskIdInput.value || "").trim(),
    };
    if (!payload.userId || !payload.taskId) {
      taskOutEl.textContent = "请先在左侧查询项目任务后，选择任务。";
      return;
    }
    const data = await postUserTaskQuery(payload);
    taskOutEl.textContent = prettyJsonWithLimit(data);
  } catch (e) {
    showErr(taskOutEl, e);
  }
});

btnAccurateWorkhour.addEventListener("click", async () => {
  try {
    const userId = (taskUserSelect.value || "").trim();
    if (!userId) {
      accurateWorkhourProgress.textContent = "精确统计失败：请先选择右侧人员（userId）。";
      return;
    }
    if (!currentFilteredTaskIds || currentFilteredTaskIds.length === 0) {
      accurateWorkhourProgress.textContent = "精确统计失败：当前没有可统计的任务候选。";
      return;
    }

    btnAccurateWorkhour.disabled = true;
    accurateWorkhourProgress.textContent = `精确统计：共 ${currentFilteredTaskIds.length} 条，逐个查询中…`;

    const summary = await accurateWorkhourByTaskIdsSequential(currentFilteredTaskIds, userId);
    accurateWorkhourProgress.textContent = `精确统计完成：有效工时=${summary.total}，命中任务=${summary.hit}（共${summary.count}条）`;

    const lines = (summary.detailRows || []).map((d) => {
      const n = d.taskName ? d.taskName : d.taskId;
      return `${n}（${d.taskId}）：${d.workhour}`;
    });
    const more = summary.count > summary.detailLimit ? `\n...（仅展示前${summary.detailLimit}条）` : "";
    workhourDetailOut.textContent = lines.join("\n") + more;
    workhourDetailOut.style.display = "block";
  } catch (e) {
    accurateWorkhourProgress.textContent = "精确统计异常：" + ((e && e.message) ? e.message : String(e));
  } finally {
    btnAccurateWorkhour.disabled = false;
  }
});

taskFilterInput.addEventListener("input", () => renderTaskSelectOptions(taskFilterInput.value));
taskExecutorSelect.addEventListener("change", () => {
  renderTaskSelectOptions(taskFilterInput.value);
  updateWorkhourSummary();
});
workhourDebugToggle.addEventListener("change", () => updateWorkhourSummary());
dueDateStartInput.addEventListener("change", forceStartDayTime);
dueDateEndInput.addEventListener("change", forceEndDayTime);

// -------- init --------
(async function init() {
  apiBaseInput.value = getApiBase();
  projectOutEl.textContent = "加载配置中...";
  taskOutEl.textContent = "加载配置中...";
  try {
    await Promise.all([loadUserOptions(), loadProjectOptions()]);
    projectOutEl.textContent = "就绪（请先查询左侧）。";
    taskOutEl.textContent = "就绪（请先查询左侧）。";
  } catch (e) {
    showErr(projectOutEl, e);
    showErr(taskOutEl, e);
  }
})();

