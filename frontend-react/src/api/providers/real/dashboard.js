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
  const res = await httpRequest('/bt/config/userids');
  const users = (res?.data || {}).users || [];
  _cachedUserids = users.map((u) => ({ name: String(u.name), userId: String(u.userId) }));
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
  const isAll = target === 'ALL';
  const resolvedNames = isAll ? userids.map((u) => u.name) : [target];
  const executorIds = resolvedNames
    .filter((nm) => nameToUserId.has(nm))
    .map((nm) => nameToUserId.get(nm));

  if (!executorIds.length && user?.name && nameToUserId.has(user.name)) {
    executorIds.push(nameToUserId.get(user.name));
  }
  return Array.from(new Set(executorIds));
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

function guessTaskTypeByContent(content) {
  const text = String(content || '');
  if (/(产品|需求|PRD|方案)/i.test(text)) return '产品';
  if (/(订单|交付|客户|验收)/i.test(text)) return '订单';
  return '研发';
}

function mapBusinessTypeLabel(v, fallbackContent = '') {
  const n = Number(v);
  if (n === 0) return '产品';
  if (n === 1) return '研发';
  if (n === 2) return '订单';
  return guessTaskTypeByContent(fallbackContent);
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

export function realFetchDepartmentOverview() {
  return httpRequest('/dashboard/department-overview');
}

export function realFetchNavTeamDetail() {
  return httpRequest('/dashboard/nav-team-detail');
}

export function realFetchIntegrationTeamDetail() {
  return httpRequest('/dashboard/integration-team-detail');
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

export function realQueryPersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const startTime = toUtcISOString(startDate);
  const endTime = toUtcISOString(endDate);
  const target = payload?.target || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      // 先取现有 dashboard 结构，避免页面字段缺失。
      const base = await httpRequest('/dashboard/personal-hours/query', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);

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
            type: mapBusinessTypeLabel(row?.business_type, taskName),
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
            prev.type = mapBusinessTypeLabel(row.business_type, taskName);
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
      const completedHours = taskDetails
        .filter((x) => x.status === '已完成')
        .reduce((sum, x) => sum + Number(x.hours || 0), 0);
      const overdueCompletedHours = taskDetails
        .filter((x) => x.quarterCategory === '季度逾期排期' && x.status === '已完成')
        .reduce((sum, x) => sum + Number(x.hours || 0), 0);

      const distributionMap = new Map([
        ['产品', 0],
        ['订单', 0],
        ['研发', 0],
      ]);
      taskDetails.forEach((x) => {
        const t = distributionMap.has(x.type) ? x.type : '研发';
        distributionMap.set(t, Number(distributionMap.get(t) || 0) + Number(x.hours || 0));
      });
      const taskDistribution = Array.from(distributionMap.entries()).map(([type, hours]) => ({
        type,
        hours,
      }));

      dashboard.scheduledEffectiveHours = quarterWorkHour;
      dashboard.completedEffectiveHours = completedHours;
      dashboard.quarterlyPlannedCompletedHours = completedHours;
      dashboard.quarterlyPlannedEffectiveHours = quarterWorkHour;
      dashboard.quarterlyOverdueEffectiveHours = quarterOverdueHour;
      dashboard.quarterlyOverdueCompletedHours = overdueCompletedHours;
      dashboard.targetLabel = targetLabel;
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
    });
}

export function realUpdatePersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const startTime = toUtcISOString(startDate);
  const endTime = toUtcISOString(endDate);
  const target = payload?.target || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
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
          message: `已触发${targetLabel}的工时更新。`,
          lastUpdatedAt: tr.lastUpdateTime || '',
        },
      };
    });
}

export function realFullUpdatePersonalHours(_user, payload) {
  const user = _user || {};
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const target = payload?.target || user?.name || 'ALL';
  const targetLabel = target === 'ALL' ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      const projectId = await fetchProjectId();
      const userids = await fetchUserids();
      const executorIds = resolveExecutorIdsByTarget(user, target, userids);
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
          message: `已触发${targetLabel}的全量更新。`,
          lastUpdatedAt: tr.lastUpdateTime || '',
        },
      };
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

export function realFetchPermissionMatrix() {
  return httpRequest('/dashboard/permission-matrix');
}
