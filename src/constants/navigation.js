import { ROUTE_PATHS } from './routes';
import { PAGE_PERMISSION_CODES } from './permissionCodes';
import { ROLES } from './roles';

export const sideMenuConfig = [
  {
    path: ROUTE_PATHS.DEPARTMENT_OVERVIEW,
    label: '部门总览',
    employeeLabel: '部门总览',
    section: '组织概览',
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.DEPARTMENT_OVERVIEW,
  },
  {
    path: ROUTE_PATHS.NAV_TEAM_DETAIL,
    label: '导航组详情',
    employeeLabel: '导航组详情',
    section: '团队管理',
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.NAV_TEAM_DETAIL,
  },
  {
    path: ROUTE_PATHS.INTEGRATION_TEAM_DETAIL,
    label: '对接组详情',
    employeeLabel: '对接组详情',
    section: '团队管理',
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.INTEGRATION_TEAM_DETAIL,
  },
  {
    path: ROUTE_PATHS.PERSONAL_HOURS,
    label: '个人工时页',
    employeeLabel: '工时管理',
    section: '个人视角',
    employeeSection: '个人工作台',
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PERSONAL_HOURS,
  },
  {
    path: ROUTE_PATHS.PERFORMANCE,
    label: '绩效页',
    employeeLabel: '绩效管理',
    section: '个人视角',
    employeeSection: '个人工作台',
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PERFORMANCE,
  },
  {
    path: ROUTE_PATHS.AI_ANALYSIS,
    label: 'AI助理',
    employeeLabel: 'AI助理',
    section: '个人视角',
    employeeSection: '个人工作台',
    allowedRoles: [ROLES.EMPLOYEE, ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.AI_ANALYSIS,
  },
  {
    path: ROUTE_PATHS.PERMISSIONS,
    label: '权限管理',
    employeeLabel: '权限管理',
    section: '系统管理',
    allowedRoles: [ROLES.MANAGER, ROLES.ADMIN],
    permissionCode: PAGE_PERMISSION_CODES.PERMISSIONS,
  },
];
