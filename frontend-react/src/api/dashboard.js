import { createApiSwitch } from './client';
import {
  mockFetchAIInsightList,
  mockCreateAITaskTicket,
  mockFetchDepartmentOverview,
  mockFetchIntegrationTeamDetail,
  mockFetchNavTeamDetail,
  mockFetchPerformanceHistory,
  mockFetchTeamPerformance,
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
  mockCreateKnowledgeChatSession,
  mockAnalyzeDashboard,
  mockApplySuggestion,
  mockFetchWorkdayCosthourTeamSummary,
  mockFetchWorkdayCosthourDeptAggregate,
  mockFetchWorkdayCosthourTaskDetail,
  mockFetchWorkdayCosthourMemberSummary,
  mockFetchWorkdayCosthourProjectNameDetail,
  mockFetchWorkdays,
  mockFetchTeamImportUsers,
  mockBatchImportScores,
  mockUpdateMemberPerformance,
  mockFetchTeams,
  mockFetchMembers,
  mockRecalcMemberPerformance,
} from './providers/mock/dashboard';
import {
  realFetchAIInsightList,
  realCreateAITaskTicket,
  realFetchDepartmentOverview,
  realFetchIntegrationTeamDetail,
  realFetchNavTeamDetail,
  realFetchPerformanceHistory,
  realFetchTeamPerformance,
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
  realCreateKnowledgeChatSession,
  realAnalyzeDashboard,
  realApplySuggestion,
  realFetchWorkdayCosthourTeamSummary,
  realFetchWorkdayCosthourDeptAggregate,
  realFetchWorkdayCosthourTaskDetail,
  realFetchWorkdayCosthourMemberSummary,
  realFetchWorkdayCosthourProjectNameDetail,
  realFetchWorkdays,
  realFetchTeamImportUsers,
  realBatchImportScores,
  realUpdateMemberPerformance,
  realFetchTeams,
  realFetchMembers,
  realRecalcMemberPerformance,
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
export const fetchTeamPerformance = createApiSwitch(mockFetchTeamPerformance, realFetchTeamPerformance);
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
export const createKnowledgeChatSession = createApiSwitch(mockCreateKnowledgeChatSession, realCreateKnowledgeChatSession);
export const analyzeDashboard = createApiSwitch(mockAnalyzeDashboard, realAnalyzeDashboard);
export const applySuggestion = createApiSwitch(mockApplySuggestion, realApplySuggestion);
export const fetchWorkdayCosthourTeamSummary = createApiSwitch(mockFetchWorkdayCosthourTeamSummary, realFetchWorkdayCosthourTeamSummary);
export const fetchWorkdayCosthourDeptAggregate = createApiSwitch(mockFetchWorkdayCosthourDeptAggregate, realFetchWorkdayCosthourDeptAggregate);
export const fetchWorkdayCosthourTaskDetail = createApiSwitch(mockFetchWorkdayCosthourTaskDetail, realFetchWorkdayCosthourTaskDetail);
export const fetchWorkdayCosthourMemberSummary = createApiSwitch(mockFetchWorkdayCosthourMemberSummary, realFetchWorkdayCosthourMemberSummary);
export const fetchWorkdayCosthourProjectNameDetail = createApiSwitch(mockFetchWorkdayCosthourProjectNameDetail, realFetchWorkdayCosthourProjectNameDetail);
export const fetchWorkdays = createApiSwitch(mockFetchWorkdays, realFetchWorkdays);

export const fetchTeamImportUsers = createApiSwitch(mockFetchTeamImportUsers, realFetchTeamImportUsers);
export const batchImportScores = createApiSwitch(mockBatchImportScores, realBatchImportScores);
export const updateMemberPerformance = createApiSwitch(mockUpdateMemberPerformance, realUpdateMemberPerformance);

export const fetchTeams = createApiSwitch(mockFetchTeams, realFetchTeams);
export const fetchMembers = createApiSwitch(mockFetchMembers, realFetchMembers);

export const recalcMemberPerformance = createApiSwitch(mockRecalcMemberPerformance, realRecalcMemberPerformance);

