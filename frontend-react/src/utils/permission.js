import { ROLE_HOME_PATH } from '../constants/routes';

export function hasRoleAccess(role, allowedRoles = []) {
  return allowedRoles.length === 0 || allowedRoles.includes(role);
}

export function hasPermissionCode(user, code) {
  return Boolean(user?.permissionCodes?.includes(code));
}

export function getDefaultHomePath(userOrRole) {
  if (typeof userOrRole === 'object' && userOrRole !== null) {
    return userOrRole.homePath ?? ROLE_HOME_PATH[userOrRole.role] ?? ROLE_HOME_PATH.employee;
  }

  return ROLE_HOME_PATH[userOrRole] ?? ROLE_HOME_PATH.employee;
}

export function getMenuRoutesByRole(routes, userOrRole) {
  const role = typeof userOrRole === 'object' && userOrRole !== null ? userOrRole.role : userOrRole;
  const permissionCodes = typeof userOrRole === 'object' && userOrRole !== null ? userOrRole.permissionCodes ?? [] : [];

  return routes.filter((route) => {
    if (!(route.menu ?? true) || !hasRoleAccess(role, route.allowedRoles)) {
      return false;
    }

    if (!route.permissionCode || permissionCodes.length === 0) {
      return true;
    }

    return permissionCodes.includes(route.permissionCode);
  });
}
