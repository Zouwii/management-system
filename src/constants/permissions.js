import { ROLES } from './roles';

export const DATA_SCOPES = {
  SELF: 'self',
  TEAM_AND_DEPARTMENT: 'team_and_department',
  ALL: 'all',
};

export const DATA_SCOPE_LABELS = {
  [DATA_SCOPES.SELF]: '本人数据',
  [DATA_SCOPES.TEAM_AND_DEPARTMENT]: '本人 + 所管组 + 部门数据',
  [DATA_SCOPES.ALL]: '全部数据',
};

export const ROLE_DATA_SCOPE_MAP = {
  [ROLES.EMPLOYEE]: DATA_SCOPES.SELF,
  [ROLES.MANAGER]: DATA_SCOPES.TEAM_AND_DEPARTMENT,
  [ROLES.ADMIN]: DATA_SCOPES.ALL,
};
