import { DATA_SCOPES, DATA_SCOPE_LABELS } from '../constants/permissions';

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
      return rows.filter((row) => row.team === user.team);
    case DATA_SCOPES.ALL:
    default:
      return rows;
  }
}

export function buildDepartmentStats(rows) {
  const navRows = rows.filter((row) => row.team === '导航组');
  const integrationRows = rows.filter((row) => row.team === '对接组');
  const hours = rows.reduce((sum, row) => sum + row.hours, 0);

  return {
    totalMembers: rows.length,
    navMembers: navRows.length,
    integrationMembers: integrationRows.length,
    totalHours: hours,
  };
}
