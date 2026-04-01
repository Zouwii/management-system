import {
  aiInsightList,
  allRows,
  integrationTeam,
  navTeam,
  performanceHistory,
  permissionMatrix,
  personalHours,
  personalHoursDashboard,
} from '../../../mock/platformData';
import { buildDepartmentStats, filterRowsByDataScope } from '../../../utils/dataScope';
import { request } from '../../request';

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

export function mockFetchPersonalHours() {
  return request(() => ({
    trend: personalHours,
    dashboard: personalHoursDashboard,
  }));
}

export function mockQueryPersonalHours(payload) {
  return request(() => ({
    trend: personalHours,
    dashboard: {
      ...personalHoursDashboard,
      defaultRange: payload,
      compensatoryDays: payload.compensatoryDays ?? personalHoursDashboard.compensatoryDays,
    },
  }));
}

export function mockUpdatePersonalHours() {
  const lastUpdatedAt = getCurrentLocalDateTime();

  return request(() => ({
    success: true,
    message: '已触发工时更新。',
    lastUpdatedAt,
  }));
}

export function mockFetchPerformanceHistory() {
  return request(() => performanceHistory);
}

export function mockFetchAIInsightList() {
  return request(() => aiInsightList);
}

export function mockFetchPermissionMatrix() {
  return request(() => permissionMatrix);
}
