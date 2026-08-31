import {
  aiInsightList,
  allRows,
  integrationTeam,
  navTeam,
  performanceArchives,
  personalHours,
  personalHoursDashboard,
} from '../../../mock/platformData';
import { buildDepartmentStats, filterRowsByDataScope } from '../../../utils/dataScope';

function delay(data, ms = 120) {
  return new Promise((resolve) => setTimeout(() => resolve(data), ms));
}
import { getDataScopeLabel } from '../../../utils/dataScope';
import { request } from '../../request';
import { httpRequest } from '../../client';
import { ROLES } from '../../../constants/roles';
import { mockAccounts, mockUsers } from '../../../mock/auth';

const ALL_TARGET = 'ALL';
const BASE_REFERENCE_HOURS = 156;
const TEAM_CODE_BY_NAME = { 导航组: 'NAV', 对接组: 'INTEGRATION', 算法组: 'ALGORITHM', 应用三组: 'APP_THREE' };
const JOB_ROLE_CODE_BY_NAME = {
  组长: 'TEAM_LEAD',
  软件开发工程师: 'SOFTWARE_ENGINEER',
  软件应用工程师: 'SOFTWARE_APPLICATION_ENGINEER',
  应用工程师: 'APPLICATION_ENGINEER',
  算法工程师: 'ALGORITHM_ENGINEER',
  实习生: 'INTERN',
};

function roundHours(value) {
  return Math.max(Math.round(value), 1);
}

function buildMemberOptions(user) {
  const rows = filterRowsByDataScope(allRows, user);
  const options = rows.map((row) => ({
    id: row.name,
    name: row.name,
    userId: row.userId || row.id || row.name,
    teamCode: row.teamCode || TEAM_CODE_BY_NAME[row.team] || '',
    teamName: row.teamName || row.team || '未分组',
    jobRoleCode: row.jobRoleCode || JOB_ROLE_CODE_BY_NAME[row.role] || 'SOFTWARE_ENGINEER',
    jobRoleName: row.jobRoleName || row.role || '软件开发工程师',
  }));

  if (user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN) {
    return [{
      id: ALL_TARGET, name: '全部人员', userId: '', teamCode: '', teamName: '全部', jobRoleCode: '', jobRoleName: '',
    }, ...options];
  }

  return options;
}

function buildPerformanceMemberOptions(user) {
  const rows = filterRowsByDataScope(allRows, user);
  const options = rows.map((row) => ({
    id: row.name,
    name: row.name,
    team: row.team,
  }));

  if (user?.name && !options.some((item) => item.id === user.name)) {
    options.unshift({
      id: user.name,
      name: user.name,
      team: user.role === ROLES.MANAGER ? '主管' : user.role === ROLES.ADMIN ? '管理员' : '个人',
    });
  }

  return options;
}

function buildPersonalHoursPayload(user, target = ALL_TARGET, payload = {}) {
  const visibleRows = filterRowsByDataScope(allRows, user);
  const memberOptions = buildMemberOptions(user);
  const canViewAll = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const fallbackTarget = canViewAll ? ALL_TARGET : user?.name;
  const targetIds = new Set(memberOptions.map((item) => item.id));
  const resolvedTarget = targetIds.has(target) ? target : fallbackTarget;
  const matchedRows = resolvedTarget === ALL_TARGET
    ? visibleRows
    : visibleRows.filter((row) => row.name === resolvedTarget);
  const totalHours = matchedRows.reduce((sum, row) => sum + row.hours, 0) || BASE_REFERENCE_HOURS;
  const scale = totalHours / BASE_REFERENCE_HOURS;
  const targetLabel = resolvedTarget === ALL_TARGET ? '全部人员' : resolvedTarget;

  return {
    memberOptions,
    selectedTarget: resolvedTarget,
    targetLabel,
    trend: personalHours.map((item) => ({
      ...item,
      total: roundHours(item.total * scale),
    })),
    dashboard: {
      ...personalHoursDashboard,
      ...payload,
      targetLabel,
      compensatoryDays: payload.compensatoryDays ?? personalHoursDashboard.compensatoryDays,
      scheduledEffectiveHours: roundHours(personalHoursDashboard.scheduledEffectiveHours * scale),
      completedEffectiveHours: roundHours(personalHoursDashboard.completedEffectiveHours * scale),
      quarterlyOverdueEffectiveHours: roundHours(personalHoursDashboard.quarterlyOverdueEffectiveHours * scale),
      quarterlyOverdueCompletedHours: roundHours(personalHoursDashboard.quarterlyOverdueCompletedHours * scale),
      quarterlyPlannedEffectiveHours: roundHours(personalHoursDashboard.quarterlyPlannedEffectiveHours * scale),
      quarterlyPlannedCompletedHours: roundHours(personalHoursDashboard.quarterlyPlannedCompletedHours * scale),
      taskDistribution: personalHoursDashboard.taskDistribution.map((item) => ({
        ...item,
        hours: roundHours(item.hours * scale),
      })),
      taskDetails: personalHoursDashboard.taskDetails.map((task) => ({
        ...task,
        hours: roundHours(task.hours * scale),
      })),
    },
  };
}

function buildPerformancePayload(user, target = user?.name) {
  const memberOptions = buildPerformanceMemberOptions(user);
  const fallbackTarget = user?.name ?? performanceArchives.李四.targetLabel;
  const targetIds = new Set(memberOptions.map((item) => item.id));
  const hasMockArchive = Object.prototype.hasOwnProperty.call(performanceArchives, target);
  const resolvedTarget = targetIds.has(target) || hasMockArchive ? target : fallbackTarget;
  const templateEntries = Object.values(performanceArchives);
  const template = performanceArchives[resolvedTarget]
    ?? templateEntries[resolvedTarget.length % templateEntries.length]
    ?? performanceArchives.李四;

  return {
    ...template,
    targetLabel: resolvedTarget,
    selectedTarget: resolvedTarget,
    memberOptions,
  };
}

export function mockFetchDepartmentOverview(user) {
  return request(() => {
    const rows = filterRowsByDataScope(allRows, user);

    return {
      stats: buildDepartmentStats(rows),
      rows,
      lastUpdatedAt: new Date().toISOString(),
    };
  });
}

function buildMockTeamEffectiveRows(items, teamCode, teamName, userIdPrefix) {
  return items.map((item, index) => {
    const completedHours = Math.max(0, 45 - index * 2);
    const overdueCompletedHours = index % 2 === 0 ? 2 : 1;
    return {
      ...item,
      userId: `${userIdPrefix}-${index + 1}`,
      teamCode,
      teamName,
      quarterExpectedHours: 52,
      scheduledHours: Math.max(0, 51 - index),
      completedHours,
      overdueEffectiveHours: 3,
      overdueCompletedHours,
    };
  });
}

export function mockFetchNavTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      buildMockTeamEffectiveRows(navTeam, 'NAV', '导航组', 'mock-nav'),
      user,
    ),
    lastUpdatedAt: new Date().toISOString(),
  }));
}

export function mockFetchIntegrationTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      buildMockTeamEffectiveRows(integrationTeam, 'INTEGRATION', '对接组', 'mock-integration'),
      user,
    ),
    lastUpdatedAt: new Date().toISOString(),
  }));
}

export function mockFetchApplicationTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      buildMockTeamEffectiveRows(navTeam.slice(0, 4), 'NAV', '导航组', 'mock-application'),
      user,
    ),
    lastUpdatedAt: new Date().toISOString(),
  }));
}

export function mockFetchAppThreeTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      buildMockTeamEffectiveRows(navTeam.slice(0, 2), 'APP_THREE', '应用三组', 'mock-app-three'),
      user,
    ),
    lastUpdatedAt: new Date().toISOString(),
  }));
}

export function mockFetchApplicationTeamReport(_user, params = {}) {
  const typeRows = [
    { label: '本体导航/导航', count: 14, ratio: 58.33 },
    { label: '本体导航/定位', count: 5, ratio: 20.83 },
    { label: '本体导航/建图', count: 3, ratio: 12.5 },
    { label: '本体导航/非本体导航', count: 2, ratio: 8.34 },
    { label: '合计', count: 24, ratio: 100 },
  ];
  const causeRows = (rows, total) => ({ rows: [...rows, { label: '合计', count: total, ratio: 100 }] });
  const typeColumns = ['本体导航/导航', '本体导航/定位', '本体导航/建图', '本体导航/非本体导航'];
  return Promise.resolve({
    code: 200,
    error: '',
    data: {
      period: { start: '2026-04-01T00:00:00', end: '2026-07-01T00:00:00' },
      scope: params?.scopeCode === 'APP_THREE_TEAM_VIEW' ? 'app_three' : 'application',
      total: 24,
      typeStats: { rows: typeRows, order: typeColumns },
      causeStats: [
        { type: '本体导航/导航', total: 14, ...causeRows([{ label: '软件bug', count: 4, ratio: 28.57 }, { label: '其他模块', count: 6, ratio: 42.86 }, { label: '外部因素', count: 4, ratio: 28.57 }], 14), secondary: {} },
        { type: '本体导航/定位', total: 5, ...causeRows([{ label: '外部因素', count: 3, ratio: 60 }, { label: '未知原因', count: 2, ratio: 40 }], 5), secondary: {} },
        { type: '本体导航/建图', total: 3, ...causeRows([{ label: '外部因素', count: 2, ratio: 66.67 }, { label: '未知原因', count: 1, ratio: 33.33 }], 3), secondary: {} },
      ],
      promptStats: [],
      handlingStats: { configured: false, rows: [] },
      priorityMatrix: { columns: typeColumns, rows: [{ label: '非常紧急', values: Object.fromEntries(typeColumns.map((item) => [item, 0])) }, { label: '紧急', values: Object.fromEntries(typeColumns.map((item) => [item, 0])) }, { label: '普通', values: Object.fromEntries(typeColumns.map((item) => [item, 0])) }] },
      documentValueMatrix: { configured: false, columns: [], rows: [] },
      projectMatrix: { columns: typeColumns, rows: [] },
      onsiteLinks: { count: 0, taskIds: [] },
      details: [],
    },
  });
}

export function mockFetchApplicationTeamOptions(_user, params = {}) {
  return Promise.resolve({
    code: 200,
    error: '',
    data: {
      members: [{ userId: 'mock-application', name: params?.scopeCode === 'APP_THREE_TEAM_VIEW' ? '应用三组示例用户' : '应用组示例用户' }],
      years: [new Date().getFullYear()],
      quarters: [1, 2, 3, 4],
      dimensions: {},
    },
  });
}

function toUtcISOString(dateTimeLocalValue) {
  const d = new Date(dateTimeLocalValue);
  if (Number.isNaN(d.getTime())) return dateTimeLocalValue;
  return d.toISOString();
}

function toLocalDateTimeInputValue(isoValue) {
  if (!isoValue) return '';
  const d = new Date(isoValue);
  if (Number.isNaN(d.getTime())) return isoValue;

  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}:${pad(d.getSeconds())}`;
}

function safeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

async function fetchProjectId() {
  const res = await httpRequest('/bt/config/projectids');
  const projects = (res?.data || {}).projects || [];
  if (!projects.length) throw new Error('missing config projectId');
  return String(projects[0].projectId);
}

async function fetchUserids() {
  const res = await httpRequest('/bt/config/userids');
  const users = (res?.data || {}).users || [];
  return users.map((u) => ({ name: String(u.name), userId: String(u.userId) }));
}

async function fetchTimeRange() {
  const res = await httpRequest('/bt/config/time_range');
  const tr = res?.data || {};
  return {
    startTime: tr.start_time || '',
    endTime: tr.end_time || '',
    lastUpdateTime: tr.last_update_time || '',
  };
}

function resolveExecutorIdsByTarget(user, target, userids) {
  const nameToUserId = new Map(userids.map((u) => [u.name, u.userId]));
  const isAll = target === ALL_TARGET;
  const resolvedNames = isAll ? userids.map((u) => u.name) : [target];
  const executorIds = resolvedNames
    .filter((nm) => nameToUserId.has(nm))
    .map((nm) => nameToUserId.get(nm));

  if (!executorIds.length && user?.name && nameToUserId.has(user.name)) {
    executorIds.push(nameToUserId.get(user.name));
  }

  return Array.from(new Set(executorIds));
}

function buildSourceTrendFromTasks(monthLabels, tasks) {
  const totalsByMonth = new Map(monthLabels.map((label) => [label, 0]));
  tasks.forEach((t) => {
    if (!t?.deadline) return;
    const parts = String(t.deadline).split('-');
    if (parts.length < 2) return;
    const monthLabel = `${Number(parts[1])}月`;
    if (!totalsByMonth.has(monthLabel)) return;
    totalsByMonth.set(monthLabel, safeNumber(totalsByMonth.get(monthLabel)) + safeNumber(t.hours));
  });

  return monthLabels.map((label) => ({
    month: label,
    total: safeNumber(totalsByMonth.get(label)),
    effective: 0,
    completed: 0,
  }));
}

function buildMonthlyLabels(startDateISO, endDateISO) {
  const start = new Date(startDateISO);
  const end = new Date(endDateISO);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return ['1月', '2月', '3月'];

  // 直接按时间区间生成去重月份标签（通常就是一个季度 3 个月）。
  const labels = [];
  const cursor = new Date(start);
  cursor.setDate(1);
  while (cursor <= end) {
    labels.push(`${cursor.getMonth() + 1}月`);
    cursor.setMonth(cursor.getMonth() + 1);
    // 防止死循环
    if (labels.length > 24) break;
  }
  return Array.from(new Set(labels));
}

async function buildPersonalHoursByQuarterAgg({ user, target, compensatoryDays }) {
  const canViewAllPeople = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const fallback = buildPersonalHoursPayload(user, target);

  try {
    const projectId = await fetchProjectId();
    const userids = await fetchUserids(); // [{name, userId}]
    const tr = await fetchTimeRange();
    const startTime = tr.startTime || '';
    const endTime = tr.endTime || '';

    let resolvedTarget = target;
    const executorIds = resolveExecutorIdsByTarget(user, target, userids);

    // 没映射到执行者则回退到当前用户
    if (!executorIds.length && user?.name) {
      resolvedTarget = user.name;
    }
    if (!executorIds.length) return fallback;

    const quarters = [];
    for (const executorId of executorIds) {
      const res = await httpRequest('/bt/stats/executor_quarter_workhours', {
        method: 'POST',
        body: JSON.stringify({
          executorId,
          projectId,
          start_time: startTime,
          end_time: endTime,
        }),
      });
      quarters.push(res?.data || {});
    }

    const first = quarters[0] || {};
    const scheduledEffectiveHours = quarters.reduce((sum, q) => sum + safeNumber(q.quarter_work_hour), 0);
    const quarterlyOverdueEffectiveHours = quarters.reduce((sum, q) => sum + safeNumber(q.quarter_overdue_work_hour), 0);
    const breakdown = quarters.flatMap((q) => (Array.isArray(q.breakdown) ? q.breakdown : []));

    const rawStart = first?.time_range?.start_time || '';
    const rawEnd = first?.time_range?.end_time || '';
    const startDate = toLocalDateTimeInputValue(rawStart);
    const endDate = toLocalDateTimeInputValue(rawEnd);

    const monthLabels = buildMonthlyLabels(rawStart, rawEnd);
    const yearFromRange = (() => {
      const y = new Date(rawStart).getFullYear();
      return Number.isFinite(y) ? y : new Date().getFullYear();
    })();

    const tasks = breakdown.map((item, idx) => {
      const isOverdue = Boolean(item?.is_overdue);
      const deadlineMonthLabel = monthLabels[idx % Math.max(monthLabels.length, 1)];
      const deadlineMonth = Number(String(deadlineMonthLabel).replace('月', ''));
      const year = yearFromRange;

      return {
        name: String(item?.content || item?.taskId || `任务-${idx + 1}`),
        type: '研发',
        hours: safeNumber(item?.work_hour),
        quarterCategory: isOverdue ? '季度逾期排期' : '当前季度排期',
        status: isOverdue ? '未完成' : '已完成',
        deadline: `${year}-${String(deadlineMonth).padStart(2, '0')}-15`,
        link: '',
        taskId: String(item?.taskId || ''),
      };
    });

    const sourceTrend = buildSourceTrendFromTasks(monthLabels, tasks);
    const targetLabel = resolvedTarget === ALL_TARGET ? '全部人员' : resolvedTarget;

    const memberOptions = canViewAllPeople
      ? [
          { id: ALL_TARGET, name: '全部人员', userId: '', teamCode: '', teamName: '全部', jobRoleCode: '', jobRoleName: '' },
          ...userids.map((u) => ({
            id: u.name,
            name: u.name,
            userId: u.userId || u.id || u.name,
            teamCode: u.name === user?.name ? user?.teamCode || '' : '',
            teamName: u.name === user?.name ? user?.teamName || '' : '未知',
            jobRoleCode: u.name === user?.name ? user?.jobRoleCode || '' : 'SOFTWARE_ENGINEER',
            jobRoleName: u.name === user?.name ? user?.jobRoleName || '' : '软件开发工程师',
          })),
        ]
      : [{
          id: user?.name || target,
          name: user?.name || target,
          userId: user?.user_id || user?.id || '',
          teamCode: user?.teamCode || '',
          teamName: user?.teamName || '',
          jobRoleCode: user?.jobRoleCode || '',
          jobRoleName: user?.jobRoleName || '',
        }];

    return {
      trend: sourceTrend,
      selectedTarget: resolvedTarget,
      memberOptions,
      dashboard: {
        ...personalHoursDashboard,
        lastUpdatedAt: tr.lastUpdateTime || '',
        compensatoryDays: Number(compensatoryDays ?? 0),
        defaultRange: {
          startDate,
          endDate,
        },
        targetLabel,
        scheduledEffectiveHours,
        completedEffectiveHours: scheduledEffectiveHours, // 默认：未逾期任务按“已完成”口径展示
        quarterlyOverdueEffectiveHours,
        quarterlyOverdueCompletedHours: 0,
        // 其余字段在当前页未使用，但保留占位保证渲染不出错
        quarterlyPlannedEffectiveHours: 0,
        quarterlyPlannedCompletedHours: 0,
        taskDetails: tasks,
        taskDistribution: [],
      },
    };
  } catch (e) {
    // 出错时至少保证页面可渲染
    console.error('[personal-hours][quarter-agg] failed:', e);
    return fallback;
  }
}

export function mockFetchPersonalHours(user, params = {}) {
  return Promise.resolve()
    .then(() => buildPersonalHoursByQuarterAgg({ user, target: params.target || ALL_TARGET, compensatoryDays: personalHoursDashboard.compensatoryDays }))
    .then((data) => ({ code: 0, message: 'ok', data }));
}

export function mockFetchPersonalHoursMembers(user) {
  const memberOptions = buildMemberOptions(user);
  const selectedTarget = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN ? ALL_TARGET : (user?.name || ALL_TARGET);
  return Promise.resolve().then(() => ({ code: 0, message: 'ok', data: { memberOptions, selectedTarget } }));
}

export function mockFetchPersonalHoursBase(user, params = {}) {
  const memberOptions = buildMemberOptions(user);
  const canViewAll = user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN;
  const selectedTarget = params.target || (canViewAll ? ALL_TARGET : (user?.name || ALL_TARGET));
  const targetLabel = selectedTarget === ALL_TARGET ? '全部人员' : selectedTarget;
  return Promise.resolve().then(() => ({
    code: 0,
    message: 'ok',
    data: {
      trend: [],
      memberOptions,
      selectedTarget,
      dashboard: {
        ...personalHoursDashboard,
        targetLabel,
      },
    },
  }));
}

export function mockQueryPersonalHours(user, payload) {
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const compensatoryDays = payload?.compensatoryDays ?? personalHoursDashboard.compensatoryDays;
  const target = payload?.target || ALL_TARGET;

  // 查询时先更新 config 时间窗，保证页面上的“预期有效工时”与后端口径一致。
  return Promise.resolve()
    .then(async () => {
      if (startDate && endDate) {
        await httpRequest('/bt/config/time_range', {
          method: 'POST',
          body: JSON.stringify({
            start_time: toUtcISOString(startDate),
            end_time: toUtcISOString(endDate),
          }),
        });
      }

      return buildPersonalHoursByQuarterAgg({ user, target, compensatoryDays });
    })
    .then((data) => ({ code: 0, message: 'ok', data }));
}

export function mockUpdatePersonalHours(user, payload) {
  const startDate = payload?.startDate || '';
  const endDate = payload?.endDate || '';
  const target = payload?.target || user?.name || ALL_TARGET;
  const targetLabel = target === ALL_TARGET ? '全部人员' : target;

  return Promise.resolve()
    .then(async () => {
      if (startDate && endDate) {
        await httpRequest('/bt/config/time_range', {
          method: 'POST',
          body: JSON.stringify({
            start_time: toUtcISOString(startDate),
            end_time: toUtcISOString(endDate),
          }),
        });
      }

      await httpRequest('/bt/config/touch_last_update_time', { method: 'POST' });
      const tr = await fetchTimeRange();
      return {
        success: true,
        selectedTarget: target,
        message: `已触发${targetLabel}的工时更新。`,
        lastUpdatedAt: tr.lastUpdateTime || '',
      };
    })
    .then((data) => ({ code: 0, message: 'ok', data }));
}

export function mockFetchPerformanceHistory(user, params = {}) {
  return request(() => buildPerformancePayload(user, params.target));
}

export function mockFetchAIInsightList() {
  return request(() => aiInsightList);
}

export function mockCreateAITaskTicket(_user, payload) {
  return request(() => ({
    success: true,
    taskId: `BT-${Math.floor(10000 + Math.random() * 90000)}`,
    taskUrl: 'https://www.teambition.com/project/mock/task/mock-task-id',
    message: `已根据 AI 草稿创建任务单：${payload.title}`,
  }));
}

export function mockCreateKnowledgeChatSession() {
  return request(() => ({ sessionId: 'mock-' + Date.now().toString(36) }));
}

export function mockAnalyzeDashboard() {
  return request(() => ({
    modules: {
      requirement_radar: { keywords: [
        {word: "导航优化", frequency: 5, suggestions: {horizontal: "扩展到叉车场景", quality: "增加RS优化参数调校", forward: "探索端到端深度学习方法"}},
        {word: "托盘识别", frequency: 3, suggestions: {horizontal: "支持异形托盘", quality: "提升遮挡场景准确率", forward: "尝试多模态大模型方案"}},
      ]},
      tech_debt_auditor: { gaps: [
        {task: "导航优化", current: "现有RS参数为经验值", target: "建立参数调校知识库", action: "输出参数调校指导文档", value_score: 8},
        {task: "托盘识别", current: "2D相机方案", target: "3D点云+纹理融合", action: "评估3D相机性价比", value_score: 7},
      ], summary: "技术债集中在感知和导航模块" },
      performance_balancer: { ratio: {assigned: 55, autonomous: 30, capability: 15}, status: "基本合规", detail: "自主型偏低，建议增加技术研究类任务", suggestions: ["每月保留20%时间做技术预研"] },
      growth_booster: { learnings: [
        {pain_point: "参数调校依赖经验", ai_tech: "贝叶斯优化 / AutoML", why_learn: "自动化调参可提升效率50%+", output_required: "输出《AutoML参数调优实践》PPT"},
      ]},
      efficiency_transformer: { tools: [
        {scenario: "每次发布手动check配置文件", tool_suggestion: "配置合规检查脚本(pre-commit hook)", expected_efficiency: "每次节省15分钟", effort_estimate: "0.5人天"},
      ]},
      risk_warning_engine: { alerts: [
        {level: "yellow", type: "结构失衡", description: "连续3周无自主型任务，建议增加技术研究"},
      ], draft_tasks: [
        {title: "【自主】导航参数自动调优工具调研", description: "调研AutoML在ROS导航参数优化中的应用，输出调研报告"},
      ]},
    },
    meta: { taskCount: 12, analyzedAt: new Date().toISOString() },
  }));
}

export function mockFetchAIModels() {
  return request(() => ({
    success: true,
    models: [
      { name: 'glm', description: '智谱，国家队老大哥', type: 'apikey' },
      { name: 'claude', description: 'Anthropic 原生模型', type: 'oauth' },
      { name: 'kimi', description: '国产四小龙之一', type: 'apikey' },
    ],
  }));
}

export function mockFetchAITtydSession(_user, payload = {}) {
  const ownerKey = String(payload?.ownerKey || _user?.user_id || _user?.userid || _user?.name || 'anonymous');
  const model = String(payload?.model || 'glm');
  const base = String(import.meta.env.VITE_AI_TTYD_URL || '').trim() || 'http://localhost:7681';
  const query = new URLSearchParams({
    ownerKey,
    model,
    expiresAt: String(Math.floor(Date.now() / 1000) + 120),
    sig: 'mock-signature',
  });
  return request(() => ({
    embedUrl: `${base}${base.includes('?') ? '&' : '?'}${query.toString()}`,
    ownerKey,
    model,
    expiresAt: Math.floor(Date.now() / 1000) + 120,
    ttlSeconds: 120,
  }));
}

export function mockInitTbcreateWorkspace() {
  return request(() => ({
    ok: true,
    workspaceDir: '(mock)',
    ownerSafe: '(mock)',
    files: { claudeMd: 'CLAUDE.md', taskContext: 'AI_TASK_CONTEXT.md', rules: 'TASK_TICKET_RULES.md' },
    taskCount: 12,
  }));
}

export function mockFetchTbcreateDraft() {
  return request(() => ({
    title: '示例任务标题',
    workType: '指派型',
    requirementDesc: '这是一个模拟的任务需求描述。在真实环境中，Claude 会将 draft.json 写入工作区，后端读取后返回给前端。',
    outputs: ['实现地图编辑功能(1.0天)', '编写单元测试(0.5天)'],
    participationLevel: 1.5,
    dueDate: new Date(Date.now() + 14 * 864e5).toISOString(),
    startDate: new Date().toISOString(),
  }));
}

export function mockSaveTbcreateDraft() {
  return request(() => ({ saved: true, savedAt: new Date().toISOString() }));
}

export function mockFetchTbcreateTasks() {
  return request(() => []);
}

export function mockFetchPermissionMatrix() {
  return request(() => Object.values(mockAccounts).map((account) => {
    const user = mockUsers[account.userKey];

    return {
      account: account.account,
      password: account.password,
      name: user?.name ?? '-',
      roleLabel: user?.roleLabel ?? '-',
      team: user?.teamName ?? '-',
      dataScopeLabel: getDataScopeLabel(user?.dataScope),
      permissionCodes: user?.permissionCodes ?? [],
    };
  }));
}

export function mockApplySuggestion() {
  return delay({ code: 200, data: { accepted: true } });
}

// ── 工作日耗时统计 Mock 数据 ──

const mockTeamSummaryData = {
  timeRange: { start_time: '2026-01-01T00:00:00', end_time: '2026-03-31T23:59:59' },
  total: { hours: 97, taskCount: 58 },
  teams: [
    {
      teamCode: 'NAV',
      teamName: '导航组',
      totalHours: 52,
      totalCount: 30,
      byProjectType: {
        '研发项目': { hours: 25, count: 15 },
        '产品项目': { hours: 18, count: 10 },
        '订单项目': { hours: 9, count: 5 },
      },
      byVehicleType: {
        '通用': { hours: 28, count: 16 },
        'AMR': { hours: 12, count: 7 },
        '叉车': { hours: 8, count: 5 },
        '非标': { hours: 4, count: 2 },
      },
      byTaskType: {
        '软件开发': { hours: 48, count: 26 },
        '问题处理': { hours: 4, count: 4 },
      },
    },
    {
      teamCode: 'INTEGRATION',
      teamName: '对接组',
      totalHours: 45,
      totalCount: 28,
      byProjectType: {
        '研发项目': { hours: 22, count: 12 },
        '产品项目': { hours: 15, count: 10 },
        '订单项目': { hours: 8, count: 6 },
      },
      byVehicleType: {
        '通用': { hours: 24, count: 14 },
        'AMR': { hours: 10, count: 6 },
        '叉车': { hours: 7, count: 5 },
        '非标': { hours: 4, count: 3 },
      },
      byTaskType: {
        '软件开发': { hours: 42, count: 24 },
        '问题处理': { hours: 3, count: 4 },
      },
    },
  ],
};

const mockDeptAggregateData = {
  timeRange: { start_time: '2026-01-01T00:00:00', end_time: '2026-03-31T23:59:59' },
  total: { hours: 97, taskCount: 58 },
  byProjectType: {
    '研发项目': { hours: 47, count: 27 },
    '产品项目': { hours: 33, count: 20 },
    '订单项目': { hours: 17, count: 11 },
  },
  byVehicleType: {
    '通用': { hours: 52, count: 30 },
    'AMR': { hours: 22, count: 13 },
    '叉车': { hours: 15, count: 10 },
    '非标': { hours: 8, count: 5 },
  },
};

const mockTaskDetailData = {
  timeRange: { start_time: '2026-01-01T00:00:00', end_time: '2026-03-31T23:59:59' },
  total: { hours: 97, taskCount: 58 },
  details: [
    {
      projectType: '研发项目',
      totalHours: 47,
      totalCount: 27,
      children: [
        { taskType: '软件开发', hours: 42.5, count: 20 },
        { taskType: '问题处理', hours: 4.5, count: 7 },
      ],
    },
    {
      projectType: '产品项目',
      totalHours: 33,
      totalCount: 20,
      children: [
        { taskType: '软件开发', hours: 30.5, count: 16 },
        { taskType: '问题处理', hours: 2.5, count: 4 },
      ],
    },
    {
      projectType: '订单项目',
      totalHours: 17,
      totalCount: 11,
      children: [
        { taskType: '软件开发', hours: 14, count: 7 },
        { taskType: '问题处理', hours: 3, count: 4 },
      ],
    },
  ],
  summary: {
    '软件开发': { hours: 87, count: 43 },
    '问题处理': { hours: 10, count: 15 },
    totalHours: 97,
    totalCount: 58,
  },
};

export function mockFetchWorkdayCosthourTeamSummary() {
  return delay({ code: 200, data: mockTeamSummaryData });
}

export function mockFetchOrganizationScopeOptions(scopeCode = '', params = {}) {
  const teamsByScope = {
    WORKDAY_COST: [
      { teamCode: 'NAV', teamName: '导航组' },
      { teamCode: 'INTEGRATION', teamName: '对接组' },
      { teamCode: 'ALGORITHM', teamName: '算法组' },
    ],
    ATTENDANCE: [
      { teamCode: 'NAV', teamName: '导航组' },
      { teamCode: 'INTEGRATION', teamName: '对接组' },
      { teamCode: 'ALGORITHM', teamName: '算法组' },
    ],
    QUARTER_PERFORMANCE: [
      { teamCode: 'NAV', teamName: '导航组' },
      { teamCode: 'INTEGRATION', teamName: '对接组' },
    ],
    APPLICATION_TEAM_VIEW: [
      { teamCode: 'NAV', teamName: '导航组' },
    ],
    APP_THREE_TEAM_VIEW: [
      { teamCode: 'APP_THREE', teamName: '应用三组' },
    ],
  };
  const teamCode = String(params?.teamCode || '').toUpperCase();
  const membersByScope = {
    QUARTER_PERFORMANCE: Object.entries({ NAV: 'nav', INTEGRATION: 'servo' })
      .filter(([code]) => !teamCode || code === teamCode)
      .flatMap(([code, key]) => mockPerformanceTeams[key].map((member) => ({
        userId: member.userId,
        userName: member.userName,
        teamCode: code,
        teamName: code === 'NAV' ? '导航组' : '对接组',
        jobRoleCode: member.jobRoleCode,
        jobRoleName: member.jobRoleName,
      }))),
    APPLICATION_TEAM_VIEW: [{ userId: 'mock-application', userName: '应用组示例用户', teamCode: 'NAV', teamName: '导航组', jobRoleCode: 'APPLICATION_ENGINEER', jobRoleName: '应用工程师' }],
    APP_THREE_TEAM_VIEW: [{ userId: 'mock-app-three', userName: '应用三组示例用户', teamCode: 'APP_THREE', teamName: '应用三组', jobRoleCode: 'SOFTWARE_ENGINEER', jobRoleName: '软件开发工程师' }],
  };
  return delay({ code: 200, data: { scopeCode, teams: teamsByScope[scopeCode] || [], members: membersByScope[scopeCode] || [] } });
}

export function mockFetchWorkdayCosthourDeptAggregate() {
  return delay({ code: 200, data: mockDeptAggregateData });
}

export function mockFetchWorkdayCosthourTaskDetail() {
  return delay({ code: 200, data: mockTaskDetailData });
}

const mockMemberSummaryData = {
  timeRange: { start_time: '2026-01-01T00:00:00', end_time: '2026-03-31T23:59:59' },
  total: { hours: 97, taskCount: 58 },
  teams: [
    { teamCode: 'NAV', teamName: '导航组' },
    { teamCode: 'INTEGRATION', teamName: '对接组' },
    { teamCode: 'ALGORITHM', teamName: '算法组' },
  ],
  members: [
    { userId: 'u1', userName: '张三', teamCode: 'NAV', teamName: '导航组', workdayCosthour: 55, taskCount: 20 },
    { userId: 'u2', userName: '李四', teamCode: 'NAV', teamName: '导航组', workdayCosthour: 42, taskCount: 10 },
    { userId: 'u3', userName: '王五', teamCode: 'INTEGRATION', teamName: '对接组', workdayCosthour: 45, taskCount: 28 },
    { userId: 'u4', userName: '赵六', teamCode: 'ALGORITHM', teamName: '算法组', workdayCosthour: 0, taskCount: 0 },
  ],
};

export function mockFetchWorkdayCosthourMemberSummary(payload = {}) {
  const teamCode = String(payload?.teamCode || '');
  const members = teamCode
    ? mockMemberSummaryData.members.filter((m) => m.teamCode === teamCode)
    : mockMemberSummaryData.members;
  return delay({ code: 200, data: { ...mockMemberSummaryData, teamCode, members } });
}

const mockProjectNameDetailData = {
  timeRange: { start_time: '2026-01-01T00:00:00', end_time: '2026-03-31T23:59:59' },
  total: { hours: 97, taskCount: 58 },
  details: [
    {
      projectType: '研发项目',
      totalHours: 65,
      totalCount: 40,
      projectNames: [
        {
          projectName: '本地图调度',
          totalHours: 25, totalCount: 15,
          children: [
            { taskType: '软件开发', hours: 15, count: 8 },
            { taskType: '问题处理', hours: 10, count: 7 },
          ],
        },
        {
          projectName: '导航协作',
          totalHours: 20, totalCount: 12,
          children: [
            { taskType: '软件开发', hours: 12, count: 6 },
            { taskType: '问题处理', hours: 8, count: 6 },
          ],
        },
        {
          projectName: '其他研发',
          totalHours: 20, totalCount: 13,
          children: [
            { taskType: '软件开发', hours: 10, count: 5 },
            { taskType: '问题处理', hours: 10, count: 8 },
          ],
        },
      ],
    },
    {
      projectType: '产品项目',
      totalHours: 20,
      totalCount: 12,
      projectNames: [
        {
          projectName: '智驾产品',
          totalHours: 12, totalCount: 7,
          children: [
            { taskType: '软件开发', hours: 7, count: 4 },
            { taskType: '问题处理', hours: 5, count: 3 },
          ],
        },
        {
          projectName: '座舱产品',
          totalHours: 8, totalCount: 5,
          children: [
            { taskType: '软件开发', hours: 5, count: 3 },
            { taskType: '问题处理', hours: 3, count: 2 },
          ],
        },
      ],
    },
    {
      projectType: '订单项目',
      totalHours: 12,
      totalCount: 6,
      projectNames: [
        {
          projectName: '吉利项目',
          totalHours: 7, totalCount: 3,
          children: [
            { taskType: '软件开发', hours: 4, count: 2 },
            { taskType: '问题处理', hours: 3, count: 1 },
          ],
        },
        {
          projectName: '比亚迪项目',
          totalHours: 5, totalCount: 3,
          children: [
            { taskType: '软件开发', hours: 3, count: 2 },
            { taskType: '问题处理', hours: 2, count: 1 },
          ],
        },
      ],
    },
  ],
};

export function mockFetchWorkdayCosthourProjectNameDetail() {
  return delay({ code: 200, data: mockProjectNameDetailData });
}

export function mockFetchWorkdays() {
  return delay({ code: 200, data: { workday_count: 59, workdays: 59, holiday_count: 7 } });
}

// ── 员工出勤表 Mock ──

export function mockFetchAttendance() {
  return delay({
    code: 200,
    data: {
      records: [
        { user_id: 'u1', user_name: '张三', teamCode: 'NAV', overtime_days: 2, leave_days: 1, statutory_holiday_days: 7, effective_work_days: 52, year: 2026, quarter: 1 },
        { user_id: 'u2', user_name: '李四', teamCode: 'INTEGRATION', overtime_days: 0, leave_days: 0.5, statutory_holiday_days: 7, effective_work_days: 52, year: 2026, quarter: 1 },
      ],
      year: 2026,
      quarter: 1,
    },
  });
}

export function mockSaveAttendance() {
  return delay({ code: 200, data: { saved_count: 2, year: 2026, quarter: 1 } });
}

// ── 绩效导入 Mock ──

const mockPerformanceTeams = {
  nav: [
    { userId: 'mock-nav-lead', userName: '导航主管', jobRoleCode: 'TEAM_LEAD', jobRoleName: '组长', isTeamLead: true },
    { userId: 'mock-nav-lisi', userName: '李四', jobRoleCode: 'SOFTWARE_ENGINEER', jobRoleName: '软件开发工程师', isTeamLead: false },
    { userId: 'mock-nav-wangqiang', userName: '王强', jobRoleCode: 'ALGORITHM_ENGINEER', jobRoleName: '算法工程师', isTeamLead: false },
    { userId: 'mock-nav-chenchen', userName: '陈晨', jobRoleCode: 'SOFTWARE_ENGINEER', jobRoleName: '软件开发工程师', isTeamLead: false },
    { userId: 'mock-nav-zhaolei', userName: '赵磊', jobRoleCode: 'ALGORITHM_ENGINEER', jobRoleName: '算法工程师', isTeamLead: false },
  ],
  servo: [
    { userId: 'mock-servo-lead', userName: '对接主管', jobRoleCode: 'TEAM_LEAD', jobRoleName: '组长', isTeamLead: true },
    { userId: 'mock-servo-suntao', userName: '孙涛', jobRoleCode: 'SOFTWARE_APPLICATION_ENGINEER', jobRoleName: '软件应用工程师', isTeamLead: false },
    { userId: 'mock-servo-zhoukai', userName: '周凯', jobRoleCode: 'SOFTWARE_APPLICATION_ENGINEER', jobRoleName: '软件应用工程师', isTeamLead: false },
    { userId: 'mock-servo-hejun', userName: '何俊', jobRoleCode: 'SOFTWARE_ENGINEER', jobRoleName: '软件开发工程师', isTeamLead: false },
    { userId: 'mock-servo-liuyang', userName: '刘洋', jobRoleCode: 'SOFTWARE_ENGINEER', jobRoleName: '软件开发工程师', isTeamLead: false },
    { userId: 'mock-servo-wubin', userName: '吴彬', jobRoleCode: 'SOFTWARE_APPLICATION_ENGINEER', jobRoleName: '软件应用工程师', isTeamLead: false },
  ],
};

const mockImportStatuses = {
  导航主管: 'archived',
  李四: 'calculated',
  王强: 'filled',
  陈晨: 'calculated',
  赵磊: null,
  对接主管: 'archived',
  孙涛: 'calculated',
  周凯: 'filled',
  何俊: 'calculated',
  刘洋: null,
  吴彬: 'calculated',
};

function buildMockImportMember(member) {
  const archive = performanceArchives[member.userName] ?? performanceArchives.李四;
  const current = archive.history[archive.history.length - 1];
  const previous = archive.history[archive.history.length - 2];
  const calcStatus = mockImportStatuses[member.userName];
  const hasInput = calcStatus !== null;
  const hasResult = calcStatus === 'calculated' || calcStatus === 'archived';

  return {
    userId: member.userId,
    userName: member.userName,
    isTeamLead: member.isTeamLead,
    workHourScore: hasInput ? current.hourScore : null,
    supervisorScore: hasInput ? current.managerScore : null,
    calcStatus,
    prevCarryBalance: previous?.carryScore ?? 0,
    prevDecayValue: previous?.decayScore ?? 0,
    overallScore: hasResult ? current.overallScore : null,
    compensationValue: hasResult ? Math.max(current.finalScore - current.balanceScore, 0) : null,
    overflowValue: hasResult ? current.overflowScore : null,
    finalScore: hasResult ? current.finalScore : null,
    newCarryBalance: hasResult ? current.carryScore : null,
    carryDecayValue: hasResult ? current.decayScore : null,
    companyScore: hasResult ? current.finalScore : null,
  };
}

export function mockFetchTeamImportUsers(params = {}) {
  const teamBucket = params.teamCode === 'INTEGRATION' ? 'servo' : 'nav';
  const members = mockPerformanceTeams[teamBucket].map(buildMockImportMember);
  return delay({ code: 200, error: '', data: { members, count: members.length } });
}

export function mockBatchImportScores() {
  return Promise.resolve({ code: 200, error: '', data: { ok: 3, fail: 0, errors: [] } });
}

export function mockUpdateMemberPerformance() {
  return Promise.resolve({ code: 200, error: '', data: { success: true } });
}

export function mockFetchTeams() {
  return delay({
    code: 200, error: '',
    data: {
      teams: [
        { teamCode: 'NAV', teamName: '导航组' },
        { teamCode: 'INTEGRATION', teamName: '对接组' },
      ],
    },
  });
}

export function mockFetchMembers(teamCode = 'NAV') {
  const resolvedTeam = teamCode === 'INTEGRATION' ? 'servo' : 'nav';
  const resolvedTeamCode = resolvedTeam === 'nav' ? 'NAV' : 'INTEGRATION';
  const teamLabel = resolvedTeam === 'nav' ? '导航组' : '对接组';
  const members = mockPerformanceTeams[resolvedTeam].map((member) => ({
    userId: member.userId,
    userName: member.userName,
    teamCode: resolvedTeamCode,
    teamName: teamLabel,
    jobRoleCode: member.isTeamLead ? 'TEAM_LEAD' : 'SOFTWARE_ENGINEER',
    jobRoleName: member.isTeamLead ? '组长' : '软件开发工程师',
  }));

  return delay({
    code: 200, error: '',
    data: {
      members,
      count: members.length,
    },
  });
}

export function mockRecalcMemberPerformance() {
  return Promise.resolve({
    code: 200,
    data: { success: true },
  });
}

export function mockIncreaseSync() {
  return Promise.resolve({
    code: 200,
    error: '',
    data: { user_count: 0, ok: 0, fail: 0, message: 'mock sync ok' },
  });
}

export function mockFetchTeamPerformance(_user, params = {}) {
  const teamBucket = params.teamCode === 'INTEGRATION' ? 'servo' : 'nav';
  const requestedYear = Number(params.year);
  const requestedQuarter = Number(params.quarter);
  const quarterLabel = `${requestedYear} Q${requestedQuarter}`;
  const results = mockPerformanceTeams[teamBucket].map((member) => {
    const archive = performanceArchives[member.userName] ?? performanceArchives.李四;
    const performance = archive.history.find((item) => item.quarter === quarterLabel);
    if (!performance) return null;

    return {
      userId: member.userId,
      userName: member.userName,
      teamCode: teamBucket === 'servo' ? 'INTEGRATION' : 'NAV',
      teamName: teamBucket === 'servo' ? '对接组' : '导航组',
      year: requestedYear,
      quarter: requestedQuarter,
      finalScore: performance.finalScore,
      newCarryBalance: performance.carryScore,
      calcStatus: mockImportStatuses[member.userName],
    };
  }).filter(Boolean);

  return delay({
    code: 200,
    error: '',
    data: { results, count: results.length },
  });
}
