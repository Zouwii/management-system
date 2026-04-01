import { ROLE_DATA_SCOPE_MAP } from '../constants/permissions';
import { ROLE_PERMISSION_CODE_MAP } from '../constants/permissionCodes';
import { ROLE_HOME_PATH } from '../constants/routes';
import { ROLE_LABELS, ROLES } from '../constants/roles';

export const mockAccounts = {
  employee: {
    account: 'employee',
    password: '123456',
    role: ROLES.EMPLOYEE,
  },
  manager: {
    account: 'manager',
    password: '123456',
    role: ROLES.MANAGER,
  },
  admin: {
    account: 'admin',
    password: '123456',
    role: ROLES.ADMIN,
  },
};

export const mockUsers = {
  [ROLES.EMPLOYEE]: {
    id: 'u-employee-li-si',
    name: '李四',
    team: '导航组',
    role: ROLES.EMPLOYEE,
    roleLabel: ROLE_LABELS[ROLES.EMPLOYEE],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.EMPLOYEE],
    permissionCodes: ROLE_PERMISSION_CODE_MAP[ROLES.EMPLOYEE],
    homePath: ROLE_HOME_PATH[ROLES.EMPLOYEE],
  },
  [ROLES.MANAGER]: {
    id: 'u-manager-wang',
    name: '王主管',
    team: '本体开发部',
    role: ROLES.MANAGER,
    roleLabel: ROLE_LABELS[ROLES.MANAGER],
    dataScope: ROLE_DATA_SCOPE_MAP[ROLES.MANAGER],
    permissionCodes: ROLE_PERMISSION_CODE_MAP[ROLES.MANAGER],
    homePath: ROLE_HOME_PATH[ROLES.MANAGER],
  },
  [ROLES.ADMIN]: {
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
