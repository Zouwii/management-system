import DepartmentOverview from '../pages/DepartmentOverview';
import NavTeamDetail from '../pages/NavTeamDetail';
import IntegrationTeamDetail from '../pages/IntegrationTeamDetail';
import PersonalHoursByRole from '../pages/PersonalHoursByRole';
import PerformancePage from '../pages/PerformancePage';
import AIAnalysisPage from '../pages/AIAnalysisPage';
import LoginPage from '../pages/LoginPage';
import Prototype from '../pages/Prototype';
import WorkdayCostHourStats from '../pages/WorkdayCostHourStats';
import AttendancePage from '../pages/AttendancePage';
import QuarterlyEffectivePerformancePage from '../pages/QuarterlyEffectivePerformancePage';
import { PAGE_PERMISSION_CODES } from '../constants/permissionCodes';
import { ROUTE_PATHS } from '../constants/routes';
import { ROLES } from '../constants/roles';

export const appRouteConfig = [
  {
    path: ROUTE_PATHS.DEPARTMENT_OVERVIEW,
    label: '有效工时',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.DEPARTMENT_OVERVIEW,
    element: <DepartmentOverview />,
  },
  {
    path: ROUTE_PATHS.NAV_TEAM_DETAIL,
    label: '导航组',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.NAV_TEAM_DETAIL,
    element: <NavTeamDetail />,
  },
  {
    path: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL,
    label: '对接组',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.INTEGRATION_TEAM_DETAIL,
    element: <IntegrationTeamDetail />,
  },
  {
    path: ROUTE_PATHS.PERSONAL_HOURS,
    label: '个人工时页',
    employeeLabel: '工时管理',
    menu: true,
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PERSONAL_HOURS,
    element: <PersonalHoursByRole />,
  },
  {
    path: ROUTE_PATHS.PERFORMANCE,
    label: '绩效页',
    employeeLabel: '绩效管理',
    menu: true,
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PERFORMANCE,
    element: <PerformancePage />,
  },
  {
    path: ROUTE_PATHS.AI_ANALYSIS,
    label: 'AI助理',
    employeeLabel: 'AI助理',
    menu: true,
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.AI_ANALYSIS,
    element: <AIAnalysisPage />,
  },
  {
    path: ROUTE_PATHS.PROTOTYPE,
    label: '完整展开版',
    menu: false,
    allowedRoles: [ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PROTOTYPE,
    element: <Prototype />,
  },
  {
    path: ROUTE_PATHS.WORKDAY_COSTHOUR,
    label: '工作日耗时',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.WORKDAY_COSTHOUR,
    element: <WorkdayCostHourStats />,
  },
  {
    path: ROUTE_PATHS.ATTENDANCE,
    label: '出勤表',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.WORKDAY_COSTHOUR,
    element: <AttendancePage />,
  },
  {
    path: ROUTE_PATHS.QUARTERLY_PERFORMANCE,
    label: '季度绩效',
    menu: true,
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.WORKDAY_COSTHOUR,
    element: <QuarterlyEffectivePerformancePage />,
  },
];

export const publicRouteConfig = [
  {
    path: ROUTE_PATHS.LOGIN,
    element: <LoginPage />,
  },
];
