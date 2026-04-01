import { createApiSwitch } from './client';
import {
  mockFetchAIInsightList,
  mockFetchDepartmentOverview,
  mockFetchIntegrationTeamDetail,
  mockFetchNavTeamDetail,
  mockFetchPerformanceHistory,
  mockFetchPermissionMatrix,
  mockFetchPersonalHours,
  mockQueryPersonalHours,
  mockUpdatePersonalHours,
} from './providers/mock/dashboard';
import {
  realFetchAIInsightList,
  realFetchDepartmentOverview,
  realFetchIntegrationTeamDetail,
  realFetchNavTeamDetail,
  realFetchPerformanceHistory,
  realFetchPermissionMatrix,
  realFetchPersonalHours,
  realQueryPersonalHours,
  realUpdatePersonalHours,
} from './providers/real/dashboard';

export const fetchDepartmentOverview = createApiSwitch(mockFetchDepartmentOverview, realFetchDepartmentOverview);
export const fetchNavTeamDetail = createApiSwitch(mockFetchNavTeamDetail, realFetchNavTeamDetail);
export const fetchIntegrationTeamDetail = createApiSwitch(mockFetchIntegrationTeamDetail, realFetchIntegrationTeamDetail);
export const fetchPersonalHours = createApiSwitch(mockFetchPersonalHours, realFetchPersonalHours);
export const queryPersonalHours = createApiSwitch(mockQueryPersonalHours, realQueryPersonalHours);
export const updatePersonalHours = createApiSwitch(mockUpdatePersonalHours, realUpdatePersonalHours);
export const fetchPerformanceHistory = createApiSwitch(mockFetchPerformanceHistory, realFetchPerformanceHistory);
export const fetchAIInsightList = createApiSwitch(mockFetchAIInsightList, realFetchAIInsightList);
export const fetchPermissionMatrix = createApiSwitch(mockFetchPermissionMatrix, realFetchPermissionMatrix);
