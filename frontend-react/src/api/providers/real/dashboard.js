import { httpRequest } from '../../client';

let _cachedProjectId = '';
let _cachedUserids = null;
let _configWarmupPromise = null;

function appendQuery(path, params = {}) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, value);
    }
  });

  const queryString = searchParams.toString();
  return queryString ? `${path}?${queryString}` : path;
}

function toUtcISOString(dateTimeLocalValue) {
  const s = String(dateTimeLocalValue || '').trim();
  if (!s) return '';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString();
}

async function fetchProjectId() {
  if (_cachedProjectId) return _cachedProjectId;
  const res = await httpRequest('/bt/config/projectids');
  const projects = (res?.data || {}).projects || [];
  if (!projects.length) throw new Error('missing config projectId');
  _cachedProjectId = String(projects[0].projectId);
  return _cachedProjectId;
}

async function fetchUserids() {
  if (Array.isArray(_cachedUserids)) return _cachedUserids;
  const res = await httpRequest('/dashboard/personal-hours/members');
  const users = (res?.data || {}).memberOptions || [];
  _cachedUserids = users.map((u) => ({
    id: String(u.id || ''),
    name: String(u.name || ''),
    userId: String(u.userId || u.id || ''),
  }));
  return _cachedUserids;
}

async function fetchLastUpdateTime() {
  const res = await httpRequest('/bt/config/last_update_time');
  const d = res?.data || {};
  return {
    lastUpdateTime: d.last_update_time || '',
  };
}

function resolveExecutorIdsByTarget(user, target, userids) {
  const nameToUserId = new Map(userids.map((u) => [u.name, u.userId]));
  const idToUserId = new Map(userids.map((u) => [u.id, u.userId]));
  const isAll = target === 'ALL';
  const normalizedTarget = String(target || '').trim();
  let executorIds = [];

  if (isAll) {
    executorIds = userids
      .map((u) => String(u.userId || '').trim())
      .filter((uid) => uid && uid !== 'ALL');
  } else if (normalizedTarget) {
    // 当前页面下拉 value 就是 user_id，优先按 user_id 直通；
    // 再兼容历史 name/id 映射，避免旧数据口径下查不到人。
    executorIds = [normalizedTarget];
    if (idToUserId.has(normalizedTarget)) {
      executorIds = [String(idToUserId.get(normalizedTarget) || '').trim()];
    } else if (nameToUserId.has(normalizedTarget)) {
      executorIds = [String(nameToUserId.get(normalizedTarget) || '').trim()];
    }
    executorIds = executorIds.filter((uid) => uid && uid !== 'ALL');
  }

  if (!executorIds.length && user?.user_id) {
    executorIds.push(String(user.user_id));
  } else if (!executorIds.length && user?.name && nameToUserId.has(user.name)) {
    executorIds.push(nameToUserId.get(user.name));
  }
  return Array.from(new Set(executorIds));
}

function resolveTargetLabelByUserids(target, userids) {
  const t = String(target || '').trim();
  if (!t || t === 'ALL') return '全部人员';
  const hit = userids.find((u) => String(u.id || '').trim() === t || String(u.userId || '').trim() === t);
  if (hit && String(hit.name || '').trim()) return String(hit.name).trim();
  return t;
}

async function warmupConfigCache() {
  if (_cachedProjectId && Array.isArray(_cachedUserids)) {
    return;
  }
  if (_configWarmupPromise) {
    return _configWarmupPromise;
  }
  _configWarmupPromise = Promise.all([fetchProjectId(), fetchUserids()])
    .then(() => undefined)
    .finally(() => {
      _configWarmupPromise = null;
    });
  return _configWarmupPromise;
}

function buildTaskLink(taskId) {
  const tid = String(taskId || '').trim();
  return tid ? `https://www.teambition.com/task/${encodeURIComponent(tid)}` : '';
}

function mapBusinessTypeLabel(v) {
  if (v === null || v === undefined || String(v).trim() === '') {
    return '无';
  }
  const n = Number(v);
  if (Number.isNaN(n)) {
    return '无';
  }
  if (n === 0) return '产品';
  if (n === 1) return '研发';
  if (n === 2) return '订单';
  return '无';
}

function mapTaskFlowStatusLabel(v) {
  const n = Number(v);
  if (n === 0) return '创建中';
  if (n === 1) return '未完成';
  if (n === 2) return '待评审';
  if (n === 3) return '评审中';
  if (n === 4) return '已完成';
  if (n === 5) return '搁置';
  return '';
}

function isUpdateBusyError(message) {
  const text = String(message || '').toLowerCase();
  return text.includes('update is in progress') || text.includes('更新中');
}

async function ensureNoGlobalUpdateLock() {
  const res = await httpRequest('/bt/update_lock_status');
  const locked = Boolean(res?.data?.locked);
  if (locked) {
    throw new Error('更新中');
  }
}

export function realFetchDepartmentOverview() {
  return httpRequest('/dashboard/department-overview');
}

export function realFetchNavTeamDetail(_user, params = {}) {
  const expected = String(params?.expected || 'quarter');
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  const pad = (n) => String(n).padStart(2, '0');
  const formatLocalInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const start = expected === 'last_quarter'
    ? new Date(quarterStartMonth === 0 ? now.getFullYear() - 1 : now.getFullYear(), quarterStartMonth === 0 ? 9 : quarterStartMonth - 3, 1, 0, 0, 0)
    : new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0);
  const end = expected === 'current'
    ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59)
    : expected === 'last_quarter'
      ? new Date(now.getFullYear(), quarterStartMonth, 0, 23, 59, 59)
      : new Date(now.getFullYear(), quarterStartMonth + 3, 0, 23, 59, 59);
  return Promise.resolve()
    .then(async () => {
      const projectId = await fetchProjectId();
      return httpRequest('/bt/stats/team_quarter_workhours', {
        method: 'POST',
        body: JSON.stringify({
          teamId: '0',
          projectId,
          start_time: formatLocalInput(start),
          end_time: formatLocalInput(end),
          exclude_character_zero: true,
        }),
      });
    })
    .then((res) => ({
      code: 200,
      error: '',
      data: {
        rows: res?.data?.rows || [],
        memberOptions: res?.data?.memberOptions || [],
        lastUpdatedAt: res?.data?.lastUpdatedAt || '',
      },
    }));
}

export function realFetchIntegrationTeamDetail(_user, params = {}) {
  const expected = String(params?.expected || 'quarter');
  const now = new Date();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  const pad = (n) => String(n).padStart(2, '0');
  const formatLocalInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const start = expected === 'last_quarter'
    ? new Date(quarterStartMonth === 0 ? now.getFullYear() - 1 : now.getFullYear(), quarterStartMonth === 0 ? 9 : quarterStartMonth - 3, 1, 0, 0, 0)
    : new Date(now.getFullYear(), quarterStartMonth, 1, 0, 0, 0);
  const end = expected === 'current'
    ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59)
    : expected === 'last_quarter'
      ? new Date(now.getFullYear(), quarterStartMonth, 0, 23, 59, 59)
      : new Date(now.getFullYear(), quarterStartMonth + 3, 0, 23, 59, 59);
  return Promise.resolve()
    .then(async () => {
      const projectId = await fetchProjectId();
      return httpRequest('/bt/stats/team_quarter_workhours', {
        method: 'POST',
        body: JSON.stringify({
          teamId: '1',
          projectId,
          start_time: formatLocalInput(start),
          end_time: formatLocalInput(end),
          exclude_character_zero: true,
        }),
      });
    })
    .then((res) => ({
      code: 200,
      error: '',
      data: {
        rows: res?.data?.rows || [],
        memberOptions: res?.data?.memberOptions || [],
        lastUpdatedAt: res?.data?.lastUpdatedAt || '',
      },
    }));
}

export function realFetchPersonalHours(_user, params = {}) {
  return Promise.resolve()
    .then(async () => {
      // 进入工时管理页时预热配置缓存，后续 query/update/fullUpdate 不再重复请求。
      await warmupConfigCache();
      // 先拿初始化默认时间窗
      const base = await httpRequest(appendQuery('/dashboard/personal-hours', {
        target: params.target,
      }));

      const dashboard = (base?.data || {}).dashboard || {};
      const defaultRange = dashboard.defaultRange || {};
      const target = (base?.data || {}).selectedTarget || params.target;

      // 再复用 query 聚合逻辑，确保首次进入页面就有后端聚合数据（而非全 0 占位）
      return realQueryPersonalHours(_user, {
        startDate: defaultRange.startDate,
        endDate: defaultRange.endDate,
        compensatoryDays: dashboard.compensatoryDays ?? 0,
        target,
      });
    });
}

export function realFetchPersonalHoursMembers() {
  return httpRequest('/dashboard/personal-hours/members');
}

export function realFetchPersonalHoursBase(_user, params = {}) {
  return httpRequest(appendQuery('/dashboard/personal-hours', {
    target: params.target,
  }));
}

export function realQueryPersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const startTime = toUtcISOString(startDate);
  const endTime = toUtcISOString(endDate);
  const target = payload?.target || user?.user_id || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      await ensureNoGlobalUpdateLock();
      // 先取现有 dashboard 结构，避免页面字段缺失。
      const base = await httpRequest('/dashboard/personal-hours/query', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
      const memberOptions = Array.isArray(base?.data?.memberOptions) ? base.data.memberOptions : [];
      const resolvedTargetLabel = resolveTargetLabelByUserids(target, memberOptions);

      let quarterWorkHour = 0;
      let quarterOverdueHour = 0;
      const mergedTaskMap = new Map();

      for (const executorId of executorIds) {
        const stats = await httpRequest('/bt/stats/executor_quarter_workhours', {
          method: 'POST',
          body: JSON.stringify({
            executorId,
            projectId,
            start_time: startTime,
            end_time: endTime,
          }),
        });
        const d = (stats?.data || {});
        quarterWorkHour += Number(d.quarter_work_hour || 0);
        quarterOverdueHour += Number(d.quarter_overdue_work_hour || 0);
        const rows = Array.isArray(d.breakdown) ? d.breakdown : [];
        for (const row of rows) {
          const taskId = String(row?.taskId || '').trim();
          if (!taskId) continue;
          const taskName = String(row?.content || taskId);
          const rawWorkHour = Number(row?.work_hour || 0);
          const hour = rawWorkHour;
          const prev = mergedTaskMap.get(taskId) || {
            taskId,
            text: taskName,
            content: taskName,
            work_hour: Number.isFinite(rawWorkHour) ? rawWorkHour : 0,
            is_overdue: Boolean(row?.is_overdue),
            business_type: row?.business_type ?? null,
            task_flow_status_id: row?.task_flow_status_id ?? null,
            name: taskName,
            type: mapBusinessTypeLabel(row?.business_type),
            quarterCategory: row?.is_overdue ? '季度逾期排期' : '当前季度排期',
            status: mapTaskFlowStatusLabel(row?.task_flow_status_id),
            hours: 0,
            due_time: String(row?.due_time || '').trim(),
            deadline: String(row?.due_time || '').trim() || String(endDate || '').slice(0, 10) || '',
            link: buildTaskLink(taskId),
          };
          // 每次合并都刷新展示字段，避免同 taskId 被空值覆盖导致前端名称为空。
          if (taskName) {
            prev.content = taskName;
            prev.text = taskName;
            prev.name = taskName;
          }
          if (row?.business_type !== undefined && row?.business_type !== null) {
            prev.business_type = row.business_type;
            prev.type = mapBusinessTypeLabel(row.business_type);
          }
          if (row?.task_flow_status_id !== undefined && row?.task_flow_status_id !== null) {
            prev.task_flow_status_id = row.task_flow_status_id;
            prev.status = mapTaskFlowStatusLabel(row.task_flow_status_id);
          }
          if (row?.due_time !== undefined && row?.due_time !== null && String(row.due_time).trim()) {
            prev.due_time = String(row.due_time).trim();
            prev.deadline = String(row.due_time).trim();
          }
          prev.hours += Number.isFinite(hour) ? hour : 0;
          // 保留 is_overdue 原始字段给后续使用；季度归属/状态按当前需求先留空。
          if (row?.is_overdue) {
            prev.is_overdue = true;
            prev.quarterCategory = '季度逾期排期';
          }
          mergedTaskMap.set(taskId, prev);
        }
      }

      const dashboard = { ...(base?.data?.dashboard || {}) };
      const taskDetails = Array.from(mergedTaskMap.values()).sort((a, b) => b.hours - a.hours);
      // “已完成”口径：按 task_flow_status_id==4 映射到的 status=已完成 汇总。
      // 并且区分当前季度排期与季度逾期排期，避免口径混淆/重复统计。
      const plannedCompletedHours = taskDetails
        .filter((x) => x.quarterCategory === '当前季度排期' && x.status === '已完成')
        .reduce((sum, x) => sum + Number(x.hours || 0), 0);
      const overdueCompletedHours = taskDetails
        .filter((x) => x.quarterCategory === '季度逾期排期' && x.status === '已完成')
        .reduce((sum, x) => sum + Number(x.hours || 0), 0);

      const distributionMap = new Map([
        ['产品', 0],
        ['订单', 0],
        ['研发', 0],
        ['无', 0],
      ]);
      taskDetails.forEach((x) => {
        const t = distributionMap.has(x.type) ? x.type : '无';
        distributionMap.set(t, Number(distributionMap.get(t) || 0) + Number(x.hours || 0));
      });
      const taskDistribution = Array.from(distributionMap.entries()).map(([type, hours]) => ({
        type,
        hours,
      }));

      dashboard.scheduledEffectiveHours = quarterWorkHour;
      dashboard.completedEffectiveHours = plannedCompletedHours;
      dashboard.quarterlyPlannedCompletedHours = plannedCompletedHours;
      dashboard.quarterlyPlannedEffectiveHours = quarterWorkHour;
      dashboard.quarterlyOverdueEffectiveHours = quarterOverdueHour;
      dashboard.quarterlyOverdueCompletedHours = overdueCompletedHours;
      dashboard.targetLabel = resolvedTargetLabel;
      dashboard.taskDetails = taskDetails;
      dashboard.taskDistribution = taskDistribution;

      return {
        ...(base || {}),
        code: 200,
        error: '',
        data: {
          ...(base?.data || {}),
          dashboard,
          selectedTarget: target,
        },
      };
    })
    .catch((error) => {
      if (isUpdateBusyError(error?.message)) {
        throw new Error('更新中');
      }
      throw error;
    });
}

export function realUpdatePersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const startTime = toUtcISOString(startDate);
  const endTime = toUtcISOString(endDate);
  const target = payload?.target || user?.user_id || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      await ensureNoGlobalUpdateLock();
      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
      const resolvedTargetLabel = resolveTargetLabelByUserids(target, userids) || targetLabel;
      for (const executorId of executorIds) {
        await httpRequest('/bt/query_project_tasks', {
          method: 'POST',
          body: JSON.stringify({
            userId: executorId,
            projectId,
            sync_ab_by_config_time_range: true,
            start_time: startTime || undefined,
            end_time: endTime || undefined,
          }),
        });
      }

      await httpRequest('/bt/config/touch_last_update_time', { method: 'POST' });
      const tr = await fetchLastUpdateTime();
      return {
        code: 200,
        error: '',
        data: {
          fullSync: false,
          message: `已触发${resolvedTargetLabel}的工时更新。`,
          lastUpdatedAt: tr.lastUpdateTime || '',
        },
      };
    })
    .catch((error) => {
      if (isUpdateBusyError(error?.message)) {
        throw new Error('更新中');
      }
      throw error;
    });
}

export function realFullUpdatePersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const target = payload?.target || user?.user_id || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      await ensureNoGlobalUpdateLock();
      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
      const resolvedTargetLabel = resolveTargetLabelByUserids(target, userids) || targetLabel;
      for (const executorId of executorIds) {
        await httpRequest('/bt/full_update', {
          method: 'POST',
          body: JSON.stringify({
            userId: executorId,
            projectId,
            maxResults: 500,
            maxPages: 200,
          }),
        });
      }

      await httpRequest('/bt/config/touch_last_update_time', { method: 'POST' });
      const tr = await fetchLastUpdateTime();
      return {
        code: 200,
        error: '',
        data: {
          fullSync: true,
          message: `已触发${resolvedTargetLabel}的全量更新。`,
          lastUpdatedAt: tr.lastUpdateTime || '',
        },
      };
    })
    .catch((error) => {
      if (isUpdateBusyError(error?.message)) {
        throw new Error('更新中');
      }
      throw error;
    });
}

export function realFetchPerformanceHistory(_user, params = {}) {
  return httpRequest(appendQuery('/dashboard/performance-history', {
    target: params.target,
  }));
}

export function realFetchAIInsightList() {
  return httpRequest('/dashboard/ai-insights');
}

export function realCreateAITaskTicket(_user, payload) {
  return httpRequest('/dashboard/ai-task-ticket', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realSendAIChatSingleTask(_user, payload) {
  return httpRequest('/bt/ai/chat/single_task', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realSendAIChatMultiTurn(_user, payload) {
  return httpRequest('/bt/ai/chat/multi_turn', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realSendAIChatSessionMessage(_user, payload) {
  return httpRequest('/bt/ai/chat/session_message', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realEndAIChatSession(_user, payload) {
  return httpRequest('/bt/ai/chat/session_end', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realFetchAIModels() {
  return httpRequest('/bt/ai/models');
}

export function realFetchPermissionMatrix() {
  return httpRequest('/dashboard/permission-matrix');
}
