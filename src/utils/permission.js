import { ROLE_HOME_PATH } from '../constants/routes';

export function hasRoleAccess(role, allowedRoles = []) {
  return allowedRoles.length === 0 || allowedRoles.includes(role);
}

export function hasPermissionCode(user, code) {
  return Boolean(user?.permissionCodes?.includes(code));
}

export function getDefaultHomePath(role) {
  return ROLE_HOME_PATH[role] ?? ROLE_HOME_PATH.employee;
}

export function getMenuRoutesByRole(routes, role) {
  return routes.filter((route) => (route.menu ?? true) && hasRoleAccess(role, route.allowedRoles));
}
