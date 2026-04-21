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
  mockSendAIChatSingleTask,
  mockSendAIChatMultiTurn,
  mockSendAIChatSessionMessage,
  mockStartAIChatSession,
  mockEndAIChatSession,
  mockFetchAIModels,
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
  realSendAIChatSingleTask,
  realSendAIChatMultiTurn,
  realSendAIChatSessionMessage,
  realStartAIChatSession,
  realEndAIChatSession,
  realFetchAIModels,
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
export const sendAIChatSingleTask = createApiSwitch(mockSendAIChatSingleTask, realSendAIChatSingleTask);
export const sendAIChatMultiTurn = createApiSwitch(mockSendAIChatMultiTurn, realSendAIChatMultiTurn);
export const sendAIChatSessionMessage = createApiSwitch(mockSendAIChatSessionMessage, realSendAIChatSessionMessage);
export const startAIChatSession = createApiSwitch(mockStartAIChatSession, realStartAIChatSession);
export const endAIChatSession = createApiSwitch(mockEndAIChatSession, realEndAIChatSession);
export const fetchAIModels = createApiSwitch(mockFetchAIModels, realFetchAIModels);
export const fetchPermissionMatrix = createApiSwitch(mockFetchPermissionMatrix, realFetchPermissionMatrix);
