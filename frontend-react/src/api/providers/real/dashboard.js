import { httpRequest } from '../../client';

let _cachedProjectId = '';
let _cachedUserids = null;
let _cachedUseridsKey = '';
let _configWarmupPromise = null;
const MEMBERS_CACHE_TTL_MS = 10 * 60 * 1000;
const MEMBERS_CACHE_KEY_PREFIX = 'personal_hours_members_cache_v1';

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

function _buildMembersCacheKey(user = {}) {
  const identity = String(user?.user_id || user?.userid || user?.name || 'anonymous').trim() || 'anonymous';
  return `${MEMBERS_CACHE_KEY_PREFIX}:${identity}`;
}

function _normalizeMemberOptions(users = []) {
  return users.map((u) => ({
    id: String(u.id || ''),
    name: String(u.name || ''),
    userId: String(u.userId || u.id || ''),
    team: String(u.team || ''),
    teamId: String(u.teamId || ''),
    character: u.character === undefined || u.character === null || String(u.character).trim() === ''
      ? null
      : Number(u.character),
  }));
}

function _readMembersCache(user = {}) {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null;
    const key = _buildMembersCacheKey(user);
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const savedAt = Number(parsed?.savedAt || 0);
    const users = Array.isArray(parsed?.users) ? parsed.users : null;
    if (!users || !savedAt) return null;
    if ((Date.now() - savedAt) > MEMBERS_CACHE_TTL_MS) {
      window.sessionStorage.removeItem(key);
      return null;
    }
    return _normalizeMemberOptions(users);
  } catch {
    return null;
  }
}

function _writeMembersCache(user = {}, users = []) {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return;
    const key = _buildMembersCacheKey(user);
    window.sessionStorage.setItem(key, JSON.stringify({
      savedAt: Date.now(),
      users,
    }));
  } catch {
    // ignore cache write failures (e.g. privacy mode/quota)
  }
}

async function fetchUserids(user = {}) {
  const key = _buildMembersCacheKey(user);
  if (Array.isArray(_cachedUserids) && _cachedUseridsKey === key) return _cachedUserids;
  const cached = _readMembersCache(user);
  if (Array.isArray(cached) && cached.length > 0) {
    _cachedUserids = cached;
    _cachedUseridsKey = key;
    return _cachedUserids;
  }
  const res = await httpRequest('/dashboard/personal-hours/members');
  const users = (res?.data || {}).memberOptions || [];
  _cachedUserids = _normalizeMemberOptions(users);
  _cachedUseridsKey = key;
  _writeMembersCache(user, users);
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

async function warmupConfigCache(user = {}) {
  if (_cachedProjectId && Array.isArray(_cachedUserids)) {
    return;
  }
  if (_configWarmupPromise) {
    return _configWarmupPromise;
  }
  _configWarmupPromise = Promise.all([fetchProjectId(), fetchUserids(user)])
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

const TASK_NATURE_VALUE_ID_TO_CODE = {
  '69d4d037c253ef42e9c31b3a': 0, // 自主型
  '69d4d037c253ef42e9c31b39': 1, // 指派型
  '69d4d037c253ef42e9c31b3b': 2, // 能力型
};

function mapTaskNatureCodeToLabel(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return '无';
  if (n === 0) return '自主型';
  if (n === 1) return '指派型';
  if (n === 2) return '能力型';
  return '无';
}

function normalizeTaskNatureCode(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  if (!s) return null;
  if (Object.prototype.hasOwnProperty.call(TASK_NATURE_VALUE_ID_TO_CODE, s)) {
    return TASK_NATURE_VALUE_ID_TO_CODE[s];
  }
  const n = Number(s);
  if (Number.isNaN(n)) return null;
  if (n === 0 || n === 1 || n === 2) return n;
  return null;
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
      await warmupConfigCache(_user || {});
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
      const userids = await fetchUserids(user);
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
      const memberOptions = Array.isArray(base?.data?.memberOptions) ? base.data.memberOptions : [];
      const resolvedTargetLabel = resolveTargetLabelByUserids(target, memberOptions);

      let quarterWorkHour = 0;
      let quarterCompletedWorkHour = 0;
      let quarterOverdueHour = 0;
      let currentQuarterWorkdayCosthourSum = 0;
      let softwareDevHour = 0;
      let issueHour = 0;
      const issueMonthlyCostHourMap = new Map();
      const mergedTaskMap = new Map();
      const mergeBreakdownRows = (rows) => {
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
            task_nature: row?.task_nature ?? null,
            task_nature_code: normalizeTaskNatureCode(row?.task_nature),
            taskNature: mapTaskNatureCodeToLabel(normalizeTaskNatureCode(row?.task_nature)),
            quarterCategory: row?.is_overdue ? '季度逾期排期' : '当前季度排期',
            status: mapTaskFlowStatusLabel(row?.task_flow_status_id),
            hours: 0,
            due_time: String(row?.due_time || '').trim(),
            parent_task_id: String(row?.parent_task_id || '').trim(),
            workday_costhour: row?.workday_costhour ?? null,
            deadline: String(row?.due_time || '').trim() || String(endDate || '').slice(0, 10) || '',
            link: buildTaskLink(taskId),
          };
          if (taskName) {
            prev.content = taskName;
            prev.text = taskName;
            prev.name = taskName;
          }
          if (row?.business_type !== undefined && row?.business_type !== null) {
            prev.business_type = row.business_type;
            prev.type = mapBusinessTypeLabel(row.business_type);
          }
          if (row?.task_nature !== undefined && row?.task_nature !== null) {
            const code = normalizeTaskNatureCode(row.task_nature);
            prev.task_nature = row.task_nature;
            prev.task_nature_code = code;
            prev.taskNature = mapTaskNatureCodeToLabel(code);
          }
          if (row?.task_flow_status_id !== undefined && row?.task_flow_status_id !== null) {
            prev.task_flow_status_id = row.task_flow_status_id;
            prev.status = mapTaskFlowStatusLabel(row.task_flow_status_id);
          }
          if (row?.due_time !== undefined && row?.due_time !== null && String(row.due_time).trim()) {
            prev.due_time = String(row.due_time).trim();
            prev.deadline = String(row.due_time).trim();
          }
          if (row?.parent_task_id !== undefined && row?.parent_task_id !== null) {
            prev.parent_task_id = String(row.parent_task_id || '').trim();
          }
          if (row?.workday_costhour !== undefined) {
            prev.workday_costhour = row?.workday_costhour ?? null;
          }
          prev.hours += Number.isFinite(hour) ? hour : 0;
          if (row?.is_overdue) {
            prev.is_overdue = true;
            prev.quarterCategory = '季度逾期排期';
          }
          mergedTaskMap.set(taskId, prev);
        }
      };

      if (target === 'ALL' && executorIds.length > 1) {
        const stats = await httpRequest('/bt/stats/executor_all_quarter_workhours', {
          method: 'POST',
          body: JSON.stringify({
            executorIds,
            projectId,
            start_time: startTime,
            end_time: endTime,
          }),
        });
        const d = stats?.data || {};
        quarterWorkHour += Number(d.quarter_work_hour || 0);
        quarterCompletedWorkHour += Number(d.quarter_completed_work_hour || 0);
        quarterOverdueHour += Number(d.quarter_overdue_work_hour || 0);
        currentQuarterWorkdayCosthourSum += Number(d.filled_cost_hour_sum ?? 0);
        softwareDevHour += Number(d.software_work_cost_hour || 0);
        issueHour += Number(d.issue_work_cost_hour || 0);
        (Array.isArray(d.issue_monthly_cost_hours) ? d.issue_monthly_cost_hours : []).forEach((row) => {
          const month = String(row?.month || '').trim();
          const hours = Number(row?.hours || 0);
          if (!month || !Number.isFinite(hours)) return;
          issueMonthlyCostHourMap.set(month, Number(issueMonthlyCostHourMap.get(month) || 0) + hours);
        });
        mergeBreakdownRows(Array.isArray(d.breakdown) ? d.breakdown : []);
      } else {
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
          const d = stats?.data || {};
          quarterWorkHour += Number(d.quarter_work_hour || 0);
          quarterCompletedWorkHour += Number(d.quarter_completed_work_hour || 0);
          quarterOverdueHour += Number(d.quarter_overdue_work_hour || 0);
          currentQuarterWorkdayCosthourSum += Number(d.filled_cost_hour_sum ?? 0);
          softwareDevHour += Number(d.software_work_cost_hour || 0);
          issueHour += Number(d.issue_work_cost_hour || 0);
          (Array.isArray(d.issue_monthly_cost_hours) ? d.issue_monthly_cost_hours : []).forEach((row) => {
            const month = String(row?.month || '').trim();
            const hours = Number(row?.hours || 0);
            if (!month || !Number.isFinite(hours)) return;
            issueMonthlyCostHourMap.set(month, Number(issueMonthlyCostHourMap.get(month) || 0) + hours);
          });
          mergeBreakdownRows(Array.isArray(d.breakdown) ? d.breakdown : []);
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
      dashboard.completedEffectiveHours = Number.isFinite(quarterCompletedWorkHour)
        ? quarterCompletedWorkHour
        : plannedCompletedHours;
      dashboard.quarterlyPlannedCompletedHours = plannedCompletedHours;
      dashboard.quarterlyPlannedEffectiveHours = quarterWorkHour;
      dashboard.quarterlyOverdueEffectiveHours = quarterOverdueHour;
      dashboard.quarterlyOverdueCompletedHours = overdueCompletedHours;
      dashboard.currentQuarterWorkdayCosthourSum = currentQuarterWorkdayCosthourSum;
      dashboard.softwareDevHours = softwareDevHour;
      dashboard.issueHandlingHours = issueHour;
      dashboard.issueMonthlyCostHours = Array.from(issueMonthlyCostHourMap.entries())
        .map(([month, hours]) => ({ month, hours }))
        .sort((a, b) => Number(String(a.month).replace('月', '')) - Number(String(b.month).replace('月', '')));
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
      const userids = await fetchUserids(user);
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
      const userids = await fetchUserids(user);
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
      const resolvedTargetLabel = resolveTargetLabelByUserids(target, userids) || targetLabel;
      // 全量更新是全项目口径，不按人员分批触发；只需一次调用即可。
      const requestUserId = String(user?.user_id || executorIds[0] || '').trim();
      if (!requestUserId) {
        throw new Error('missing userId');
      }
      await httpRequest('/bt/full_update', {
        method: 'POST',
        body: JSON.stringify({
          userId: requestUserId,
          projectId,
          maxResults: 500,
          maxPages: 200,
        }),
      });

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
  }).catch(() => ({
    code: 200,
    error: '',
    data: {
      result: {
        status: 'success',
        result: `本地降级回复：已收到任务请求 - ${String(payload?.prompt || '').slice(0, 120)}`,
      },
    },
  }));
}

export function realSendAIChatMultiTurn(_user, payload) {
  return httpRequest('/bt/ai/chat/multi_turn', {
    method: 'POST',
    body: JSON.stringify(payload),
  }).catch(() => ({
    code: 200,
    error: '',
    data: {
      result: {
        rounds: Array.isArray(payload?.prompts)
          ? payload.prompts.map((p, idx) => ({
            round: idx + 1,
            prompt: p,
            response: { result: `本地降级回复：${String(p || '').slice(0, 120)}` },
          }))
          : [],
      },
    },
  }));
}

export function realSendAIChatSessionMessage(_user, payload) {
  return httpRequest('/bt/ai/chat/session_message', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realStartAIChatSession(_user, payload) {
  return httpRequest('/bt/ai/chat/session_start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realEndAIChatSession(_user, payload) {
  return httpRequest('/bt/ai/chat/session_end', {
    method: 'POST',
    body: JSON.stringify(payload),
  }).catch(() => ({
    code: 200,
    error: '',
    data: {
      conversationId: payload?.conversationId || '',
      ended: false,
      message: '本地降级：未连接后端会话接口',
    },
  }));
}

export function realFetchAIModels() {
  return httpRequest('/bt/ai/models').catch(() => ({
    code: 200,
    error: '',
    data: {
      models: [
        { name: 'glm', description: '默认模型（本地降级）' },
      ],
    },
  }));
}

export function realFetchAITtydSession(_user, payload = {}) {
  return httpRequest('/bt/ai/ttyd/session', {
    method: 'POST',
    body: JSON.stringify(payload || {}),
  });
}

export function realFetchPermissionMatrix() {
  return httpRequest('/dashboard/permission-matrix');
}
