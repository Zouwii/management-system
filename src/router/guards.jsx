import { Navigate, useLocation } from 'react-router-dom';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getDefaultHomePath, hasRoleAccess } from '../utils/permission';

export function ProtectedRoute({ allowedRoles, children }) {
  const location = useLocation();
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const requiredCode = children.props.permissionCode;

  if (!isAuthenticated || !user) {
    return <Navigate to={ROUTE_PATHS.LOGIN} replace state={{ from: location.pathname }} />;
  }

  if (!hasRoleAccess(user.role, allowedRoles)) {
    return <Navigate to={getDefaultHomePath(user)} replace />;
  }

  if (requiredCode && !hasPermission(requiredCode)) {
    return <Navigate to={getDefaultHomePath(user)} replace />;
  }

  return children;
}

export function PublicOnlyRoute({ children }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  if (isAuthenticated && user) {
    return <Navigate to={getDefaultHomePath(user)} replace />;
  }

  return children;
}

export function RootRedirect() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  if (!isAuthenticated || !user) {
    return <Navigate to={ROUTE_PATHS.LOGIN} replace />;
  }

  return <Navigate to={getDefaultHomePath(user)} replace />;
}
