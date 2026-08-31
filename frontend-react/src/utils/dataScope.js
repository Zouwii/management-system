import { DATA_SCOPES, DATA_SCOPE_LABELS } from '../constants/permissions';

const TEAM_CODE_BY_LABEL = {
  '导航组': 'NAV',
  '对接组': 'INTEGRATION',
  '算法组': 'ALGORITHM',
  '应用三组': 'APP_THREE',
};

function teamCode(value = {}) {
  return value.teamCode || TEAM_CODE_BY_LABEL[value.team] || '';
}

export function getDataScopeLabel(scope) {
  return DATA_SCOPE_LABELS[scope] ?? '未知数据范围';
}

export function filterRowsByDataScope(rows, user) {
  if (!user) {
    return [];
  }

  switch (user.dataScope) {
    case DATA_SCOPES.SELF:
      return rows.filter((row) => row.name === user.name);
    case DATA_SCOPES.TEAM:
      return rows.filter((row) => teamCode(row) === teamCode(user));
    case DATA_SCOPES.ALL:
    default:
      return rows;
  }
}

export function buildDepartmentStats(rows) {
  const navRows = rows.filter((row) => teamCode(row) === 'NAV');
  const integrationRows = rows.filter((row) => teamCode(row) === 'INTEGRATION');
  const hours = rows.reduce((sum, row) => sum + row.hours, 0);

  return {
    totalMembers: rows.length,
    navMembers: navRows.length,
    integrationMembers: integrationRows.length,
    totalHours: hours,
  };
}
