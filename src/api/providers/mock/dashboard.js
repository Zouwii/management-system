import {
  aiInsightList,
  allRows,
  integrationTeam,
  navTeam,
  performanceArchives,
  permissionMatrix,
  personalHours,
  personalHoursDashboard,
} from '../../../mock/platformData';
import { buildDepartmentStats, filterRowsByDataScope } from '../../../utils/dataScope';
import { request } from '../../request';
import { ROLES } from '../../../constants/roles';

const ALL_TARGET = 'ALL';
const BASE_REFERENCE_HOURS = 156;

function getCurrentLocalDateTime() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

function roundHours(value) {
  return Math.max(Math.round(value), 1);
}

function buildMemberOptions(user) {
  const rows = filterRowsByDataScope(allRows, user);
  const options = rows.map((row) => ({
    id: row.name,
    name: row.name,
    team: row.team,
  }));

  if (user?.role === ROLES.MANAGER || user?.role === ROLES.ADMIN) {
    return [{ id: ALL_TARGET, name: '全部人员', team: '全部' }, ...options];
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

function buildPerformancePayload(user) {
  return performanceArchives[user?.name] ?? performanceArchives.李四;
}

export function mockFetchDepartmentOverview(user) {
  return request(() => {
    const rows = filterRowsByDataScope(allRows, user);

    return {
      stats: buildDepartmentStats(rows),
      rows,
    };
  });
}

export function mockFetchNavTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      navTeam.map((item) => ({ ...item, team: '导航组' })),
      user,
    ),
  }));
}

export function mockFetchIntegrationTeamDetail(user) {
  return request(() => ({
    rows: filterRowsByDataScope(
      integrationTeam.map((item) => ({ ...item, team: '对接组' })),
      user,
    ),
  }));
}

export function mockFetchPersonalHours(user, params = {}) {
  return request(() => buildPersonalHoursPayload(user, params.target));
}

export function mockQueryPersonalHours(user, payload) {
  return request(() => buildPersonalHoursPayload(user, payload.target, {
    defaultRange: {
      startDate: payload.startDate,
      endDate: payload.endDate,
    },
    compensatoryDays: payload.compensatoryDays ?? personalHoursDashboard.compensatoryDays,
  }));
}

export function mockUpdatePersonalHours(user, payload) {
  const lastUpdatedAt = getCurrentLocalDateTime();
  const { selectedTarget, targetLabel } = buildPersonalHoursPayload(user, payload.target);

  return request(() => ({
    success: true,
    selectedTarget,
    message: `已触发${targetLabel}的工时更新。`,
    lastUpdatedAt,
  }));
}

export function mockFetchPerformanceHistory(user) {
  return request(() => buildPerformancePayload(user));
}

export function mockFetchAIInsightList() {
  return request(() => aiInsightList);
}

export function mockFetchPermissionMatrix() {
  return request(() => permissionMatrix);
}
