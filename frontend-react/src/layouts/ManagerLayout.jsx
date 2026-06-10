import { useState } from 'react';
import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getMenuRoutesByRole, hasRoleAccess } from '../utils/permission';

export default function ManagerLayout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.MANAGER;
  const menus = getMenuRoutesByRole(sideMenuConfig, user ?? role).map((route) => ({
    label: route.label,
    section: route.section,
    to: route.path,
    children: (route.children || [])
      .filter((child) => hasRoleAccess(role, child.allowedRoles))
      .map((child) => ({ label: child.label, to: child.path })),
  }));

  const subtitle = role === ROLES.ADMIN
    ? `${ROLE_LABELS[role]} / 全局权限`
    : `${user?.team ?? '团队'}主管 / 组级权限`;

  const note = '';

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className={collapsed ? 'col-span-1' : 'col-span-2'}>
        <SideMenu
          title="本体开发部数据管理平台"
          subtitle={subtitle}
          menus={menus}
          theme="dark"
          logoSrc="/竖版-中文(1).png"
          logoAlt="迦智科技"
          note={note}
          actionLabel="退出登录"
          actionTo={ROUTE_PATHS.LOGIN}
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((prev) => !prev)}
        />
      </aside>
      <main className={collapsed ? 'col-span-11 space-y-6' : 'col-span-10 space-y-6'}>{children}</main>
    </div>
  );
}
