import { useState } from 'react';
import SideMenu from '../components/SideMenu';
import { sideMenuConfig } from '../constants/navigation';
import { ROLE_LABELS, ROLES } from '../constants/roles';
import { ROUTE_PATHS } from '../constants/routes';
import { useAuthStore } from '../store/authStore';
import { getDataScopeLabel } from '../utils/dataScope';
import { getMenuRoutesByRole } from '../utils/permission';

export default function ManagerLayout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((state) => state.user);
  const role = user?.role ?? ROLES.MANAGER;
  const menus = getMenuRoutesByRole(sideMenuConfig, user ?? role).map((route) => ({
    label: route.label,
    section: route.section,
    to: route.path,
  }));

  const subtitle = role === ROLES.ADMIN
    ? `${ROLE_LABELS[role]} / 全局权限`
    : `${user?.team ?? '团队'}主管 / 组级权限`;

  const note = role === ROLES.ADMIN
    ? `管理员可访问全部页面与全部数据，当前数据范围：${getDataScopeLabel(user?.dataScope)}。`
    : `主管仅可查看本人和所管团队数据，不可访问部门页和其他团队页。当前数据范围：${getDataScopeLabel(user?.dataScope)}。`;

  return (
    <div className="grid grid-cols-12 gap-6">
      <aside className={collapsed ? 'col-span-1' : 'col-span-3'}>
        <SideMenu
          title="本体开发部数据平台"
          subtitle={subtitle}
          menus={menus}
          theme="dark"
          note={note}
          actionLabel="退出登录"
          actionTo={ROUTE_PATHS.LOGIN}
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((prev) => !prev)}
        />
      </aside>
      <main className={collapsed ? 'col-span-11 space-y-6' : 'col-span-9 space-y-6'}>{children}</main>
    </div>
  );
}
