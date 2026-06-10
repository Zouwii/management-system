import { ROLES } from './roles';

export const ROUTE_PATHS = {
  ROOT: '/',
  LOGIN: '/login',
  PROTOTYPE: '/prototype',
  DEPARTMENT_OVERVIEW: '/manager/department-overview',
  NAV_TEAM_DETAIL: '/manager/nav-team-detail',
  INTEGRATION_TEAM_DETAIL: '/manager/integration-team-detail',
  PERSONAL_HOURS: '/employee/personal-hours',
  PERFORMANCE: '/employee/performance',
  AI_ANALYSIS: '/employee/ai-analysis',
  PERMISSIONS: '/manager/permissions',
  WORKDAY_COSTHOUR: '/manager/workday-costhour',
};

export const ROLE_HOME_PATH = {
  [ROLES.EMPLOYEE]: ROUTE_PATHS.PERSONAL_HOURS,
  [ROLES.MANAGER]: ROUTE_PATHS.NAV_TEAM_DETAIL,
  [ROLES.ADMIN]: ROUTE_PATHS.DEPARTMENT_OVERVIEW,
  navManager: ROUTE_PATHS.NAV_TEAM_DETAIL,
  servoManager: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL,
};
