import { httpRequest } from '../../client';

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
  return httpRequest(appendQuery('/dashboard/personal-hours', {
    target: params.target,
  }));
}

export function realQueryPersonalHours(_user, payload) {
  return httpRequest('/dashboard/personal-hours/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realUpdatePersonalHours(_user, payload) {
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

export function realCreateAITaskTicket(_user, payload) {
  return httpRequest('/dashboard/ai-task-ticket', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function realFetchPermissionMatrix() {
  return httpRequest('/dashboard/permission-matrix');
}
