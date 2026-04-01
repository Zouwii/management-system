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
    },
  }));
}

export function mockUpdatePersonalHours(payload) {
  return request(() => ({
    success: true,
    message: `已根据 ${payload.startDate} 至 ${payload.endDate} 的时间区间触发更新`,
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
