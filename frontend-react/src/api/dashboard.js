import { createApiSwitch } from './client';
import {
  mockFetchAIInsightList,
  mockCreateAITaskTicket,
  mockFetchDepartmentOverview,
  mockFetchIntegrationTeamDetail,
  mockFetchNavTeamDetail,
  mockFetchPerformanceHistory,
  mockFetchPermissionMatrix,
  mockFetchPersonalHours,
  mockFetchPersonalHoursMembers,
  mockFetchPersonalHoursBase,
  mockQueryPersonalHours,
  mockUpdatePersonalHours,
  mockUpdatePersonalHours as mockFullUpdatePersonalHours,
  mockFetchAIModels,
  mockFetchAITtydSession,
  mockInitTbcreateWorkspace,
  mockFetchTbcreateDraft,
  mockSaveTbcreateDraft,
  mockFetchTbcreateTasks,
  mockSyncKnowledgeBase,
  mockFetchAIKnowledgeTtydSession,
} from './providers/mock/dashboard';
import {
  realFetchAIInsightList,
  realCreateAITaskTicket,
  realFetchDepartmentOverview,
  realFetchIntegrationTeamDetail,
  realFetchNavTeamDetail,
  realFetchPerformanceHistory,
  realFetchPermissionMatrix,
  realFetchPersonalHours,
  realFetchPersonalHoursMembers,
  realFetchPersonalHoursBase,
  realQueryPersonalHours,
  realUpdatePersonalHours,
  realFullUpdatePersonalHours,
  realFetchAIModels,
  realFetchAITtydSession,
  realInitTbcreateWorkspace,
  realFetchTbcreateDraft,
  realSaveTbcreateDraft,
  realFetchTbcreateTasks,
  realSyncKnowledgeBase,
  realFetchAIKnowledgeTtydSession,
} from './providers/real/dashboard';

export const fetchDepartmentOverview = createApiSwitch(mockFetchDepartmentOverview, realFetchDepartmentOverview);
export const fetchNavTeamDetail = createApiSwitch(mockFetchNavTeamDetail, realFetchNavTeamDetail);
export const fetchIntegrationTeamDetail = createApiSwitch(mockFetchIntegrationTeamDetail, realFetchIntegrationTeamDetail);
export const fetchPersonalHours = createApiSwitch(mockFetchPersonalHours, realFetchPersonalHours);
export const fetchPersonalHoursMembers = createApiSwitch(mockFetchPersonalHoursMembers, realFetchPersonalHoursMembers);
export const fetchPersonalHoursBase = createApiSwitch(mockFetchPersonalHoursBase, realFetchPersonalHoursBase);
export const queryPersonalHours = createApiSwitch(mockQueryPersonalHours, realQueryPersonalHours);
export const updatePersonalHours = createApiSwitch(mockUpdatePersonalHours, realUpdatePersonalHours);
export const fullUpdatePersonalHours = createApiSwitch(mockFullUpdatePersonalHours, realFullUpdatePersonalHours);
export const fetchPerformanceHistory = createApiSwitch(mockFetchPerformanceHistory, realFetchPerformanceHistory);
export const fetchAIInsightList = createApiSwitch(mockFetchAIInsightList, realFetchAIInsightList);
export const createAITaskTicket = createApiSwitch(mockCreateAITaskTicket, realCreateAITaskTicket);
export const fetchAIModels = createApiSwitch(mockFetchAIModels, realFetchAIModels);
export const fetchAITtydSession = createApiSwitch(mockFetchAITtydSession, realFetchAITtydSession);
export const initTbcreateWorkspace = createApiSwitch(
  mockInitTbcreateWorkspace,
  realInitTbcreateWorkspace,
);
export const fetchTbcreateDraft = createApiSwitch(
  mockFetchTbcreateDraft,
  realFetchTbcreateDraft,
);
export const saveTbcreateDraft = createApiSwitch(
  mockSaveTbcreateDraft,
  realSaveTbcreateDraft,
);
export const fetchTbcreateTasks = createApiSwitch(
  mockFetchTbcreateTasks,
  realFetchTbcreateTasks,
);
export const fetchPermissionMatrix = createApiSwitch(mockFetchPermissionMatrix, realFetchPermissionMatrix);
export const syncKnowledgeBase = createApiSwitch(mockSyncKnowledgeBase, realSyncKnowledgeBase);
export const fetchAIKnowledgeTtydSession = createApiSwitch(mockFetchAIKnowledgeTtydSession, realFetchAIKnowledgeTtydSession);
