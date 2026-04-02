import { ROLE_DATA_SCOPE_MAP } from '../constants/permissions';
import { PAGE_PERMISSION_CODES, ROLE_PERMISSION_CODE_MAP } from '../constants/permissionCodes';
import { ROLE_HOME_PATH } from '../constants/routes';
import { ROLE_LABELS, ROLES } from '../constants/roles';

export const mockAccounts = {
  employee: {
    account: 'employee',
    password: '123456',
    userKey: 'employee',
  },
  navManager: {
    account: 'navManager',
    password: '123456',
    userKey: 'navManager',
  },
  servoManager: {
    account: 'servoManager',
    password: '123456',
    userKey: 'servoManager',
  },
  admin: {
    account: 'admin',
    password: '123456',
    userKey: 'admin',
  },
};

export const mockUsers = {
  employee: {
    id: 'u-employee-li-si',
    name: '李四',
    team: '导航组',
    role: ROLES.EMPLOYEE,
    roleLabel: ROLE_LABELS[ROLES.EMPLOYEE],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.EMPLOYEE],
    permissionCodes: ROLE_PERMISSION_CODE_MAP[ROLES.EMPLOYEE],
    homePath: ROLE_HOME_PATH[ROLES.EMPLOYEE],
  },
  navManager: {
    id: 'u-manager-nav',
    name: '导航主管',
    team: '导航组',
    role: ROLES.MANAGER,
    roleLabel: ROLE_LABELS[ROLES.MANAGER],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.MANAGER],
    permissionCodes: [
      PAGE_PERMISSION_CODES.NAV_TEAM_DETAIL,
      PAGE_PERMISSION_CODES.PERSONAL_HOURS,
      PAGE_PERMISSION_CODES.PERFORMANCE,
      PAGE_PERMISSION_CODES.AI_ANALYSIS,
      ...ROLE_PERMISSION_CODE_MAP[ROLES.MANAGER].filter((code) => String(code).startsWith('button.')),
    ],
    homePath: ROLE_HOME_PATH.navManager,
  },
  servoManager: {
    id: 'u-manager-servo',
    name: '对接主管',
    team: '对接组',
    role: ROLES.MANAGER,
    roleLabel: ROLE_LABELS[ROLES.MANAGER],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.MANAGER],
    permissionCodes: [
      PAGE_PERMISSION_CODES.INTEGRATION_TEAM_DETAIL,
      PAGE_PERMISSION_CODES.PERSONAL_HOURS,
      PAGE_PERMISSION_CODES.PERFORMANCE,
      PAGE_PERMISSION_CODES.AI_ANALYSIS,
      ...ROLE_PERMISSION_CODE_MAP[ROLES.MANAGER].filter((code) => String(code).startsWith('button.')),
    ],
    homePath: ROLE_HOME_PATH.servoManager,
  },
  admin: {
    id: 'u-admin-system',
    name: '系统管理员',
    team: '平台管理',
    role: ROLES.ADMIN,
    roleLabel: ROLE_LABELS[ROLES.ADMIN],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.ADMIN],
    permissionCodes: ROLE_PERMISSION_CODE_MAP[ROLES.ADMIN],
    homePath: ROLE_HOME_PATH[ROLES.ADMIN],
  },
};
