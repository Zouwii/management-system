import { httpRequest } from '../../client';

export function realFetchDepartmentOverview() {
  return httpRequest('/dashboard/department-overview');
}

export function realFetchNavTeamDetail() {
  return httpRequest('/dashboard/nav-team-detail');
}

export function realFetchIntegrationTeamDetail() {
  return httpRequest('/dashboard/integration-team-detail');
}

export function realFetchPersonalHours() {
  return httpRequest('/dashboard/personal-hours');
}

export function realQueryPersonalHours(payload) {
  return httpRequest('/dashboard/personal-hours/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realUpdatePersonalHours(payload) {
  return httpRequest('/dashboard/personal-hours/update', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realFetchPerformanceHistory() {
  return httpRequest('/dashboard/performance-history');
}

export function realFetchAIInsightList() {
  return httpRequest('/dashboard/ai-insights');
}

export function realFetchPermissionMatrix() {
  return httpRequest('/dashboard/permission-matrix');
}
