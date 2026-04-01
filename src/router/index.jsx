import { Navigate, Route, Routes } from 'react-router-dom';
import { ROUTE_PATHS } from '../constants/routes';
import { ProtectedRoute, PublicOnlyRoute, RootRedirect } from './guards';
import { appRouteConfig, publicRouteConfig } from './routeConfig';

function PageContainer({ children }) {
  return <div className="min-h-screen bg-slate-100 p-6 text-slate-900">{children}</div>;
}

export default function AppRouter() {
  return (
    <Routes>
      <Route path={ROUTE_PATHS.ROOT} element={<RootRedirect />} />
      {publicRouteConfig.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={(
            <PublicOnlyRoute>
              <PageContainer>{route.element}</PageContainer>
            </PublicOnlyRoute>
          )}
        />
      ))}
      {appRouteConfig.map((route) => (
        <Route
          key={route.path}
          path={route.path}
          element={(
            <ProtectedRoute allowedRoles={route.allowedRoles}>
              <PageContainer permissionCode={route.permissionCode}>{route.element}</PageContainer>
            </ProtectedRoute>
          )}
        />
      ))}
      <Route path="*" element={<Navigate to={ROUTE_PATHS.ROOT} replace />} />
    </Routes>
  );
}
