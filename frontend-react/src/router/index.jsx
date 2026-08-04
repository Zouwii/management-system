import { Navigate, Route, Routes } from 'react-router-dom';
import SessionExpiredModal from '../components/SessionExpiredModal';
import { ROUTE_PATHS } from '../constants/routes';
import { ProtectedRoute, PublicOnlyRoute, RootRedirect } from './guards';
import { appRouteConfig, publicRouteConfig } from './routeConfig';

function PageContainer({ children }) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.14),_transparent_24%),radial-gradient(circle_at_top_right,_rgba(16,185,129,0.1),_transparent_20%),linear-gradient(180deg,_#eef4fb_0%,_#e2ecf8_46%,_#edf3f8_100%)] p-3 text-slate-900 sm:p-4 lg:p-6">
      {children}
    </div>
  );
}

export default function AppRouter() {
  return (
    <>
      <SessionExpiredModal />
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
    </>
  );
}
